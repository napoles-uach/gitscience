"""Trusted small-twist scaling experiment for the helicoidal ribbon."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any

import numpy as np

from .schema import TransportRequest


@dataclass(frozen=True)
class SmallTwistRequest:
    """Validated parameters for a symmetric small-twist sweep."""

    width: int
    length: int
    energy: float
    tau_values: list[float]
    hopping: float = 1.0
    soc: float = 0.1
    onsite: float = 0.0
    linearity_tolerance: float = 0.06
    quadratic_tolerance: float = 0.05
    symmetry_tolerance: float = 1e-7
    numerical_tolerance: float = 1e-9

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> SmallTwistRequest:
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown twist-sweep parameters: {', '.join(unknown)}")
        try:
            request = cls(**values)
        except TypeError as exc:
            raise ValueError(f"Invalid twist-sweep request: {exc}") from exc
        request.validate()
        return request

    def validate(self) -> None:
        TransportRequest.from_mapping(
            {
                "width": self.width,
                "length": self.length,
                "energy": self.energy,
                "tau": 0.0,
                "hopping": self.hopping,
                "soc": self.soc,
                "onsite": self.onsite,
                "compare_opposite_tau": False,
                "check_zero_twist": False,
                "check_soc_zero": False,
                "symmetry_tolerance": self.symmetry_tolerance,
                "numerical_tolerance": self.numerical_tolerance,
            }
        )
        if not isinstance(self.tau_values, list) or len(self.tau_values) < 4:
            raise ValueError(
                "tau_values must contain at least four non-negative points"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            for value in self.tau_values
        ):
            raise TypeError("tau_values must contain finite numbers")
        normalized = [float(value) for value in self.tau_values]
        if normalized != sorted(set(normalized)):
            raise ValueError("tau_values must be sorted and unique")
        if normalized[0] != 0.0 or any(value < 0 for value in normalized):
            raise ValueError("tau_values must start at zero and be non-negative")
        if normalized[-1] > 0.2:
            raise ValueError("small-twist sweeps require max(tau_values) <= 0.2")
        for name in ("linearity_tolerance", "quadratic_tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a finite number")
            if not isfinite(float(value)) or not 0 < value < 1:
                raise ValueError(f"{name} must be between zero and one")

    def point_request(self) -> TransportRequest:
        return TransportRequest.from_mapping(
            {
                "width": self.width,
                "length": self.length,
                "energy": self.energy,
                "tau": float(self.tau_values[-1]),
                "hopping": self.hopping,
                "soc": self.soc,
                "onsite": self.onsite,
                "compare_opposite_tau": False,
                "check_zero_twist": False,
                "check_soc_zero": False,
                "symmetry_tolerance": self.symmetry_tolerance,
                "numerical_tolerance": self.numerical_tolerance,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PointSolver = Callable[[TransportRequest, float, float | None], dict[str, Any]]


def _default_solver(
    request: TransportRequest, tau: float, soc: float | None = None
) -> dict[str, Any]:
    from .twisted_nanoribbon import solve_transport_point

    return solve_transport_point(request, tau, soc)


def _diagnostics(run: dict[str, Any], tolerance: float) -> dict[str, bool]:
    return {
        "hermitian": run["hermiticity_residual"] <= tolerance,
        "unitary": run["unitarity_residual"] <= tolerance,
        "spin_decomposition_consistent": run["transmission_decomposition_residual"]
        <= tolerance,
        "lead_modes_matched": run["lead_block_nmodes"][0]
        == run["lead_block_nmodes"][1],
    }


def run_small_twist_experiment(
    values: dict[str, Any], solver: PointSolver | None = None
) -> dict[str, Any]:
    """Measure parity and leading small-twist scaling from symmetric Kwant runs."""
    request = SmallTwistRequest.from_mapping(values)
    point_request = request.point_request()
    solve = solver or _default_solver
    runs: dict[str, dict[str, Any]] = {}

    zero = solve(point_request, 0.0, None)
    runs["tau_+0"] = zero
    magnitudes = np.asarray(request.tau_values, dtype=float)
    polarization_odd = [float(zero["polarization_x"] or 0.0)]
    transmission_even = [float(zero["transmission"])]
    polarization_even_residuals = [abs(float(zero["polarization_x"] or 0.0))]
    transmission_odd_residuals = [0.0]

    for tau in magnitudes[1:]:
        plus = solve(point_request, float(tau), None)
        minus = solve(point_request, -float(tau), None)
        runs[f"tau_+{tau:g}"] = plus
        runs[f"tau_-{tau:g}"] = minus
        px_plus = plus.get("polarization_x")
        px_minus = minus.get("polarization_x")
        if px_plus is None or px_minus is None:
            raise RuntimeError(f"Polarization unavailable at tau={tau:g}")
        polarization_odd.append(0.5 * (px_plus - px_minus))
        polarization_even_residuals.append(abs(0.5 * (px_plus + px_minus)))
        transmission_even.append(0.5 * (plus["transmission"] + minus["transmission"]))
        transmission_odd_residuals.append(
            abs(0.5 * (plus["transmission"] - minus["transmission"]))
        )

    px_values = np.asarray(polarization_odd)
    transmission_values = np.asarray(transmission_even)
    slope = float(np.dot(magnitudes, px_values) / np.dot(magnitudes, magnitudes))
    px_fit = slope * magnitudes
    px_scale = max(float(np.max(np.abs(px_values))), 1e-15)
    px_relative_residual = float(np.max(np.abs(px_values - px_fit)) / px_scale)

    tau_squared = magnitudes**2
    quadratic_coefficient, intercept = np.polyfit(tau_squared, transmission_values, 1)
    transmission_fit = intercept + quadratic_coefficient * tau_squared
    transmission_scale = max(
        float(np.max(np.abs(transmission_values - transmission_values[0]))), 1e-15
    )
    transmission_relative_residual = float(
        np.max(np.abs(transmission_values - transmission_fit)) / transmission_scale
    )

    px_parity_residual = max(polarization_even_residuals)
    transmission_parity_residual = max(transmission_odd_residuals)
    claims = {
        "polarization_linear_in_small_twist": {
            "passes": px_relative_residual <= request.linearity_tolerance
            and px_parity_residual <= request.symmetry_tolerance,
            "slope": slope,
            "relative_max_residual": px_relative_residual,
            "even_component_max_abs": px_parity_residual,
            "tolerance": request.linearity_tolerance,
        },
        "transmission_quadratic_in_small_twist": {
            "passes": transmission_relative_residual <= request.quadratic_tolerance
            and transmission_parity_residual <= request.symmetry_tolerance,
            "intercept": float(intercept),
            "quadratic_coefficient": float(quadratic_coefficient),
            "relative_max_residual": transmission_relative_residual,
            "odd_component_max_abs": transmission_parity_residual,
            "tolerance": request.quadratic_tolerance,
        },
    }
    return {
        "schema_version": "kwant-twist-scaling-v1",
        "model": "effective-square-lattice-helicoidal-ribbon-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "request": request.to_dict(),
        "runs": runs,
        "series": {
            "tau_magnitudes": magnitudes.tolist(),
            "polarization_odd": px_values.tolist(),
            "polarization_linear_fit": px_fit.tolist(),
            "transmission_even": transmission_values.tolist(),
            "transmission_quadratic_fit": transmission_fit.tolist(),
        },
        "claims": claims,
        "diagnostics": {
            name: _diagnostics(run, request.numerical_tolerance)
            for name, run in runs.items()
        },
    }
