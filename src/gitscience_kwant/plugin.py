"""GitScience plugin contract for the trusted Kwant experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runner import run_transport_experiment
from .schema import TransportRequest
from .twist_sweep import SmallTwistRequest, run_small_twist_experiment

POINT_ASSERTIONS = frozenset(
    {
        "transmission_even_in_tau",
        "polarization_x_odd_in_tau",
        "zero_twist_polarization",
        "zero_soc_polarization",
        "numerical_diagnostics",
    }
)
SWEEP_ASSERTIONS = frozenset(
    {
        "polarization_linear_in_small_twist",
        "transmission_quadratic_in_small_twist",
        "numerical_diagnostics",
    }
)


@dataclass(frozen=True)
class KwantTransportVerifier:
    """Trusted, schema-limited verifier for the helicoidal ribbon model."""

    name: str = "kwant_transport"
    version: str = "0.1.0"
    default_experiment: str = "point_symmetry"
    artifact_suffix: str = ".kwant.json"
    evidence_kind: str = "computational_experiment"
    environment_packages: tuple[str, ...] = (
        "kwant",
        "numpy",
        "scipy",
        "tinyarray",
    )

    def validate(
        self, experiment: str, request: dict[str, Any], assertions: list[str]
    ) -> None:
        if experiment == "point_symmetry":
            TransportRequest.from_mapping(request)
            allowed = POINT_ASSERTIONS
        elif experiment == "small_twist_scaling":
            SmallTwistRequest.from_mapping(request)
            allowed = SWEEP_ASSERTIONS
        else:
            raise ValueError(f"Unsupported Kwant experiment: {experiment}")
        unknown = sorted(set(assertions) - allowed)
        if unknown:
            raise ValueError(f"Unsupported assertions: {', '.join(unknown)}")

    def run(self, experiment: str, request: dict[str, Any]) -> dict[str, Any]:
        if experiment == "point_symmetry":
            return run_transport_experiment(request)
        if experiment == "small_twist_scaling":
            return run_small_twist_experiment(request)
        raise ValueError(f"Unsupported Kwant experiment: {experiment}")

    def source_paths(self) -> list[Path]:
        return sorted(Path(__file__).parent.glob("*.py"))


plugin = KwantTransportVerifier()
