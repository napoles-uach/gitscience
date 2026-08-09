"""Effective spinful tight-binding model of a helicoidal nanoribbon."""

import numpy as np

from .schema import TransportRequest

SIGMA_X = np.array([[0, 1], [1, 0]], dtype=complex)
SIGMA_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
SIGMA_Z = np.array([[1, 0], [0, -1]], dtype=complex)
IDENTITY = np.eye(2, dtype=complex)
PAULI = np.array([SIGMA_X, SIGMA_Y, SIGMA_Z])


def _embedding(x: float, y: float, tau: float) -> np.ndarray:
    angle = tau * x
    return np.array([x, y * np.cos(angle), y * np.sin(angle)])


def _normal(x: float, y: float, tau: float) -> np.ndarray:
    angle = tau * x
    dx = np.array([1.0, -tau * y * np.sin(angle), tau * y * np.cos(angle)])
    dy = np.array([0.0, np.cos(angle), np.sin(angle)])
    normal = np.cross(dx, dy)
    return normal / np.linalg.norm(normal)


def _spin_dot(vector: np.ndarray) -> np.ndarray:
    return sum(vector[index] * PAULI[index] for index in range(3))


def build_system(request: TransportRequest, tau: float, soc: float | None = None):
    """Build a finite helicoidal ribbon with two ideal spin-conserving leads."""
    try:
        import kwant
    except ImportError as exc:
        raise RuntimeError(
            "Kwant is not installed. Create the environment from "
            "the GitScience environments/kwant-transport.yml file."
        ) from exc

    spin_orbit = request.soc if soc is None else soc
    lattice = kwant.lattice.square(norbs=2)
    system = kwant.Builder()
    onsite_matrix = (4.0 * request.hopping + request.onsite) * IDENTITY

    for x in range(request.length):
        for y in range(request.width):
            system[lattice(x, y)] = onsite_matrix

    center = 0.5 * (request.width - 1)

    def scattering_hopping(site_a, site_b):
        x_a, y_a = site_a.tag
        x_b, y_b = site_b.tag
        y_a -= center
        y_b -= center
        point_a = _embedding(x_a, y_a, tau)
        point_b = _embedding(x_b, y_b, tau)
        direction = point_b - point_a
        direction /= np.linalg.norm(direction)
        normal = _normal(0.5 * (x_a + x_b), 0.5 * (y_a + y_b), tau)
        rashba_axis = np.cross(normal, direction)
        return -request.hopping * IDENTITY + 1j * spin_orbit * _spin_dot(rashba_axis)

    system[lattice.neighbors()] = scattering_hopping

    lead = kwant.Builder(kwant.TranslationalSymmetry((-1, 0)), conservation_law=SIGMA_X)
    for y in range(request.width):
        lead[lattice(0, y)] = onsite_matrix
    lead[lattice.neighbors()] = -request.hopping * IDENTITY
    system.attach_lead(lead)
    system.attach_lead(lead.reversed())
    return system.finalized()


def solve_transport_point(
    request: TransportRequest, tau: float, soc: float | None = None
) -> dict:
    """Evaluate transmission, x-spin polarization, and numerical diagnostics."""
    try:
        import kwant
    except ImportError as exc:
        raise RuntimeError(
            "Kwant is not installed. Create the environment from "
            "the GitScience environments/kwant-transport.yml file."
        ) from exc

    system = build_system(request, tau=tau, soc=soc)
    hamiltonian = system.hamiltonian_submatrix(sparse=False)
    hermiticity_residual = float(
        np.max(np.abs(hamiltonian - hamiltonian.conjugate().T), initial=0.0)
    )
    smatrix = kwant.smatrix(system, request.energy, check_hermiticity=True)
    scattering = smatrix.data
    identity = np.eye(scattering.shape[1], dtype=complex)
    unitarity_residual = float(
        np.max(np.abs(scattering.conjugate().T @ scattering - identity), initial=0.0)
    )

    transmission = float(smatrix.transmission(1, 0))
    incoming_blocks = range(len(smatrix.lead_info[0].block_nmodes))
    outgoing_blocks = len(smatrix.lead_info[1].block_nmodes)
    if outgoing_blocks != 2:
        raise RuntimeError(
            "Expected two sigma_x lead blocks; the selected energy may have an "
            "unsupported lead-mode structure."
        )
    spin_minus = sum(
        float(smatrix.transmission((1, 0), (0, block))) for block in incoming_blocks
    )
    spin_plus = sum(
        float(smatrix.transmission((1, 1), (0, block))) for block in incoming_blocks
    )
    polarized_total = spin_plus + spin_minus
    transmission_decomposition_residual = abs(transmission - polarized_total)
    polarization_x = (
        (spin_plus - spin_minus) / polarized_total
        if polarized_total > request.numerical_tolerance
        else None
    )

    return {
        "tau": float(tau),
        "soc": float(request.soc if soc is None else soc),
        "energy": float(request.energy),
        "transmission": transmission,
        "spin_transmission_minus_x": spin_minus,
        "spin_transmission_plus_x": spin_plus,
        "polarization_x": polarization_x,
        "transmission_decomposition_residual": transmission_decomposition_residual,
        "hermiticity_residual": hermiticity_residual,
        "unitarity_residual": unitarity_residual,
        "lead_block_nmodes": [
            list(map(int, info.block_nmodes)) for info in smatrix.lead_info
        ],
        "hamiltonian_dimension": int(hamiltonian.shape[0]),
    }
