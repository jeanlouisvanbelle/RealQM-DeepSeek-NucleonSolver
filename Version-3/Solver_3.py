import numpy as np
from scipy.optimize import minimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
import traceback
import time

# ============================================================
# 1. PHYSICAL CONSTANTS
# ============================================================
e = 1.602176634e-19
m_p = 1.67262192369e-27
m_n = 1.67492749804e-27
c = 299792458.0
h = 6.62607015e-34
hbar = h / (2 * np.pi)
mu0 = 4e-7 * np.pi
epsilon0 = 1 / (mu0 * c**2)
alpha = e**2 / (4 * np.pi * epsilon0 * hbar * c)

MeV = 1.602176634e-13
m_p_c2_MeV = m_p * c**2 / MeV
m_n_c2_MeV = m_n * c**2 / MeV
fm = 1e-15

print("=" * 80)
print("RealQM Nuclear Solver V3.3 - Gaussian Repulsion")
print("=" * 80)
print(f"Proton mass: {m_p_c2_MeV:.4f} MeV/c²")
print(f"Neutron mass: {m_n_c2_MeV:.4f} MeV/c²")
print(f"Fine-structure constant: {alpha:.6f}")
print("=" * 80)

# ============================================================
# 2. COHERENCE FUNCTIONS
# ============================================================
def coherence_fraction(E, eta_0, E0):
    return 1 - (1 - eta_0) * np.exp(-E / E0)

def local_field_strength(r, coupling_order=3):
    if r == 0:
        return 1e6
    return 1.0 / (r ** coupling_order)

NEUTRON_ETA_0 = 0.676
NEUTRON_E0 = 0.5
PROTON_ETA_0 = 1.0
PROTON_E0 = 1.5

print("✓ Coherence functions loaded.")

# ============================================================
# 3. NEUMANN INDUCTANCE ENGINE
# ============================================================
def generate_loop_points(center, tilt, yaw, radius=0.8415e-15, steps=16):
    t = np.linspace(0, 2 * np.pi, steps, endpoint=False)
    base_points = np.zeros((steps, 3))
    base_points[:, 0] = radius * np.cos(t)
    base_points[:, 1] = radius * np.sin(t)
    cos_t, sin_t = np.cos(tilt), np.sin(tilt)
    cos_y, sin_y = np.cos(yaw), np.sin(yaw)
    R_tilt = np.array([[1.0, 0.0, 0.0], [0.0, cos_t, -sin_t], [0.0, sin_t, cos_t]])
    R_yaw = np.array([[cos_y, -sin_y, 0.0], [sin_y, cos_y, 0.0], [0.0, 0.0, 1.0]])
    return np.dot(base_points, np.dot(R_yaw, R_tilt).T) + center

def calculate_mutual_inductance(loop1, loop2):
    n = len(loop1)
    dl1 = np.zeros((n, 3))
    dl1[:-1] = loop1[1:] - loop1[:-1]
    dl1[-1] = loop1[0] - loop1[-1]
    dl2 = np.zeros((n, 3))
    dl2[:-1] = loop2[1:] - loop2[:-1]
    dl2[-1] = loop2[0] - loop2[-1]
    diff = loop1[:, np.newaxis, :] - loop2[np.newaxis, :, :]
    r12 = np.linalg.norm(diff, axis=2)
    core_buffer = 0.1e-15
    r12 = np.where(r12 < core_buffer, core_buffer, r12)
    M = (mu0 / (4 * np.pi)) * np.sum(np.sum(dl1[:, np.newaxis, :] * dl2[np.newaxis, :, :], axis=2) / r12)
    return M

def calculate_self_inductance(loop, radius, q, I):
    a_wire = 0.1e-15
    L = mu0 * radius * (np.log(8 * radius / a_wire) - 2)
    return L

def calculate_coulomb_energy(q1, q2, r):
    if r == 0:
        return 1e6
    return (1 / (4 * np.pi * epsilon0)) * q1 * q2 / r

print("✓ Neumann inductance engine loaded.")

# ============================================================
# 4. GEOMETRY DEFINITIONS
# ============================================================
def geometry_deuteron():
    centers = np.array([[-1.0 * fm, 0.0, 0.0], [1.0 * fm, 0.0, 0.0]])
    identities = np.array([0, 1])
    return centers, identities

def geometry_triton():
    centers = np.array([[0.0, 0.0, 0.0], [0.0, 1.2 * fm, 0.0], [0.0, -0.8 * fm, 0.8 * fm]])
    identities = np.array([0, 1, 1])
    return centers, identities

def geometry_alpha():
    side = 2.8 * fm
    s = side / np.sqrt(2)
    centers = np.array([
        [s/2, 0.0, -s/(2*np.sqrt(2))],
        [-s/2, 0.0, -s/(2*np.sqrt(2))],
        [0.0, s/2, s/(2*np.sqrt(2))],
        [0.0, -s/2, s/(2*np.sqrt(2))]
    ])
    identities = np.array([0, 0, 1, 1])
    return centers, identities

def geometry_boron11():
    alpha1 = np.array([-1.4 * fm, 0.0, 0.0])
    alpha2 = np.array([1.4 * fm, 0.0, 0.0])
    triton = np.array([0.0, 1.8 * fm, 0.0])
    centers = []
    identities = []
    a1_centers, a1_ids = geometry_alpha()
    centers.extend(a1_centers + alpha1)
    identities.extend(a1_ids)
    a2_centers, a2_ids = geometry_alpha()
    centers.extend(a2_centers + alpha2)
    identities.extend(a2_ids)
    t_centers, t_ids = geometry_triton()
    centers.extend(t_centers + triton)
    identities.extend(t_ids)
    return np.array(centers), np.array(identities)

def geometry_oxygen16():
    R_aa = 2.8 * fm
    r_loop = 0.8415 * fm
    s = R_aa / np.sqrt(2)
    alpha_centers = np.array([
        [s/2, 0.0, -s/(2*np.sqrt(2))],
        [-s/2, 0.0, -s/(2*np.sqrt(2))],
        [0.0, s/2, s/(2*np.sqrt(2))],
        [0.0, -s/2, s/(2*np.sqrt(2))]
    ])
    d = r_loop / np.sqrt(2)
    loop_offsets = np.array([
        [d/2, 0.0, -d/(2*np.sqrt(2))],
        [-d/2, 0.0, -d/(2*np.sqrt(2))],
        [0.0, d/2, d/(2*np.sqrt(2))],
        [0.0, -d/2, d/(2*np.sqrt(2))]
    ])
    loop_centers, loop_types = [], []
    for a_center in alpha_centers:
        for idx, offset in enumerate(loop_offsets):
            loop_centers.append(a_center + offset)
            loop_types.append(0 if idx < 2 else 1)
    return np.array(loop_centers), np.array(loop_types)

print("✓ Geometry definitions loaded.")

# ============================================================
# 5. NUCLEON SOLVER V3.3 (Gaussian Repulsion)
# ============================================================
class NucleonSolverV3_3:
    def __init__(self, geometry_function, name="Unnamed"):
        self.name = name
        self.centers_initial, self.identities = geometry_function()
        self.n_loops = len(self.centers_initial)
        self.n_params = 5 * self.n_loops
        self.I_p = e * (m_p * c**2 / h)
        self.I_n_base = e * (m_n * c**2 / h)
        self.neutron_eta_0 = NEUTRON_ETA_0
        self.neutron_E0 = NEUTRON_E0
        self.proton_eta_0 = PROTON_ETA_0
        self.proton_E0 = PROTON_E0
        self.U0 = None
        self.U_min = None
        self.delta_E = None
        self.kappa = None
        print(f"  {name}: {self.n_loops} loops, {self.n_params} DOF")

    def compute_eta_for_nucleon(self, idx, centers):
        center = centers[idx]
        E_total = 0.0
        for j, other in enumerate(centers):
            if j == idx:
                continue
            r = np.linalg.norm(center - other)
            E_total += local_field_strength(r, coupling_order=3)
        if self.identities[idx] == 0:
            return coherence_fraction(E_total, self.proton_eta_0, self.proton_E0)
        else:
            return coherence_fraction(E_total, self.neutron_eta_0, self.neutron_E0)

    def compute_currents(self, centers):
        currents = []
        for idx, identity in enumerate(self.identities):
            eta = self.compute_eta_for_nucleon(idx, centers)
            if identity == 0:
                currents.append(self.I_p * eta)
            else:
                currents.append(self.I_n_base * eta)
        return currents

    def unpack_params(self, params):
        centers = np.zeros((self.n_loops, 3))
        angles = np.zeros((self.n_loops, 2))
        for i in range(self.n_loops):
            centers[i] = params[5*i : 5*i + 3]
            angles[i] = params[5*i + 3 : 5*i + 5]
        return centers, angles

    def calculate_energy(self, params):
        centers, angles = self.unpack_params(params)
        loops = []
        for i in range(self.n_loops):
            loops.append(generate_loop_points(centers[i], angles[i, 0], angles[i, 1]))
        currents = self.compute_currents(centers)
        charges = [e if self.identities[i] == 0 else 0.0 for i in range(self.n_loops)]
        total_energy_joules = 0.0
        radius = 0.8415e-15

        # 1. Self-inductance
        for i in range(self.n_loops):
            L_ii = calculate_self_inductance(loops[i], radius, charges[i], currents[i])
            total_energy_joules += 0.5 * L_ii * currents[i]**2

        # 2. Mutual inductance
        for i in range(self.n_loops):
            for j in range(i + 1, self.n_loops):
                M_ij = calculate_mutual_inductance(loops[i], loops[j])
                total_energy_joules += M_ij * currents[i] * currents[j]

        # 3. Coulomb
        for i in range(self.n_loops):
            for j in range(i + 1, self.n_loops):
                if self.identities[i] == 0 and self.identities[j] == 0:
                    r = np.linalg.norm(centers[i] - centers[j])
                    total_energy_joules += calculate_coulomb_energy(e, e, r)

        # 4. Kinetic energy
        for i in range(self.n_loops):
            if self.identities[i] == 0:
                total_energy_joules += 0.5 * m_p * c**2
            else:
                total_energy_joules += 0.5 * m_n * c**2

        # 5. Gaussian repulsion (smooth and physical)
        repulsion_strength = 1.0  # MeV
        r0 = 1.0 * fm
        for i in range(self.n_loops):
            for j in range(i + 1, self.n_loops):
                r = np.linalg.norm(centers[i] - centers[j])
                if r > 0:
                    total_energy_joules += repulsion_strength * MeV * np.exp(-(r / r0) ** 2)

        return total_energy_joules / MeV

    def solve(self, verbose=True):
        static_params = np.zeros(self.n_params)
        for i in range(self.n_loops):
            static_params[5*i : 5*i + 3] = self.centers_initial[i]
        self.U0 = self.calculate_energy(static_params)
        if verbose:
            print(f"    Static baseline: {self.U0:.4f} MeV")

        half_range = 0.5 * fm
        bounds = []
        for i in range(self.n_loops):
            bounds.extend([
                (self.centers_initial[i, 0] - half_range, self.centers_initial[i, 0] + half_range),
                (self.centers_initial[i, 1] - half_range, self.centers_initial[i, 1] + half_range),
                (self.centers_initial[i, 2] - half_range, self.centers_initial[i, 2] + half_range)
            ])
            bounds.extend([(-np.pi/12, np.pi/12), (-np.pi/12, np.pi/12)])

        np.random.seed(42)
        initial_params = static_params.copy()
        for i in range(self.n_params):
            initial_params[i] += np.random.uniform(-0.01, 0.01) * fm if i < 3*self.n_loops else np.random.uniform(-0.01, 0.01)

        start_time = time.time()
        result = minimize(
            self.calculate_energy,
            initial_params,
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 500, 'ftol': 1e-6}
        )
        elapsed = time.time() - start_time

        self.U_min = result.fun
        self.delta_E = self.U0 - self.U_min
        self.kappa = 127.6200 / self.delta_E if self.delta_E > 0 else np.inf

        if verbose:
            print(f"    Relaxed: {self.U_min:.4f} MeV")
            print(f"    ΔE: {self.delta_E:.4f} MeV")
            print(f"    kappa: {self.kappa:.4f}")
            print(f"    Time: {elapsed:.1f} s")
            print(f"    Converged: {result.success}")

        self.final_centers, self.final_angles = self.unpack_params(result.x)
        return result

print("✓ NucleonSolverV3.3 ready (Gaussian repulsion).")

# ============================================================
# 6. MAIN EXECUTION
# ============================================================
if __name__ == "__main__":
    try:
        nuclei = {
            "Deuteron": geometry_deuteron,
            "Triton": geometry_triton,
            "Alpha": geometry_alpha,
            "Boron-11": geometry_boron11,
            "Oxygen-16": geometry_oxygen16,
        }

        results = {}

        print("\n" + "=" * 80)
        print("STARTING FULL SOLVER V3.3")
        print("=" * 80 + "\n")

        for name, geom in nuclei.items():
            print(f"\n{'─' * 60}")
            print(f"Solving: {name}")
            print(f"{'─' * 60}")
            solver = NucleonSolverV3_3(geom, name)
            solver.solve(verbose=True)
            results[name] = solver

        print("\n" + "=" * 80)
        print("SUMMARY OF RESULTS")
        print("=" * 80)
        print(f"{'Nucleus':<12} | {'U0 (MeV)':>12} | {'U_min (MeV)':>12} | {'ΔE (MeV)':>12} | {'kappa':>10}")
        print("-" * 80)
        for name, solver in results.items():
            print(f"{name:<12} | {solver.U0:>12.4f} | {solver.U_min:>12.4f} | {solver.delta_E:>12.4f} | {solver.kappa:>10.4f}")
        print("=" * 80)

        print("\n" + "=" * 80)
        print("SOLVER V3.3 COMPLETED")
        print("=" * 80)

    except Exception as e:
        print("\n" + "=" * 80)
        print("ERROR OCCURRED:")
        print("=" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        print("\nTraceback:")
        traceback.print_exc()
        print("=" * 80)

    print("\nPress Enter to exit...")
    input()
