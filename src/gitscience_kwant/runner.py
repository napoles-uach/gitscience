"""Experiment orchestration and claim checks for the Kwant adapter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .schema import TransportRequest

Solver = Callable[[TransportRequest, float, float | None], dict[str, Any]]


def _default_solver(
    request: TransportRequest, tau: float, soc: float | None = None
) -> dict[str, Any]:
    from .twisted_nanoribbon import solve_transport_point

    return solve_transport_point(request, tau, soc)


def _residual(value: float, reference: float) -> dict[str, float]:
    absolute = abs(value - reference)
    scale = max(abs(value), abs(reference), 1e-15)
    return {"absolute": absolute, "relative": absolute / scale}


def run_transport_experiment(
    values: dict[str, Any], solver: Solver | None = None
) -> dict[str, Any]:
    """Run the requested physical points and evaluate the prototype claims."""
    request = TransportRequest.from_mapping(values)
    solve = solver or _default_solver
    runs: dict[str, dict[str, Any]] = {"plus_tau": solve(request, request.tau, None)}
    claims: dict[str, dict[str, Any]] = {}

    if request.compare_opposite_tau:
        runs["minus_tau"] = solve(request, -request.tau, None)
        plus = runs["plus_tau"]
        minus = runs["minus_tau"]
        transmission_even = _residual(plus["transmission"], minus["transmission"])
        transmission_even["passes"] = (
            transmission_even["absolute"] <= request.symmetry_tolerance
        )
        px_plus = plus.get("polarization_x")
        px_minus = minus.get("polarization_x")
        px_odd = None
        if px_plus is not None and px_minus is not None:
            absolute = abs(px_plus + px_minus)
            px_odd = {
                "absolute": absolute,
                "passes": absolute <= request.symmetry_tolerance,
            }
        claims["transmission_even_in_tau"] = transmission_even
        claims["polarization_x_odd_in_tau"] = px_odd

    if request.check_zero_twist:
        runs["zero_tau"] = solve(request, 0.0, None)
        px = runs["zero_tau"].get("polarization_x")
        claims["zero_twist_polarization"] = {
            "absolute": None if px is None else abs(px),
            "passes": None if px is None else abs(px) <= request.symmetry_tolerance,
        }

    if request.check_soc_zero:
        runs["zero_soc"] = solve(request, request.tau, 0.0)
        px = runs["zero_soc"].get("polarization_x")
        claims["zero_soc_polarization"] = {
            "absolute": None if px is None else abs(px),
            "passes": None if px is None else abs(px) <= request.symmetry_tolerance,
        }

    diagnostics = {
        name: {
            "hermitian": run["hermiticity_residual"] <= request.numerical_tolerance,
            "unitary": run["unitarity_residual"] <= request.numerical_tolerance,
            "spin_decomposition_consistent": run["transmission_decomposition_residual"]
            <= request.numerical_tolerance,
            "lead_modes_matched": run["lead_block_nmodes"][0]
            == run["lead_block_nmodes"][1],
        }
        for name, run in runs.items()
    }
    return {
        "schema_version": "kwant-transport-v1",
        "model": "effective-square-lattice-helicoidal-ribbon-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "request": request.to_dict(),
        "runs": runs,
        "claims": claims,
        "diagnostics": diagnostics,
    }
