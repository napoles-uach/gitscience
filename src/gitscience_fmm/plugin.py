"""Schema-limited verifier for quantum-FMM occupancy-tail claims."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .occupancy import run_occupancy_regime_experiment
from .schema import OccupancyRegimeRequest

ASSERTIONS = frozenset(
    {
        "constant_mean_tail_budget",
        "proportional_mean_tail_budget",
        "hybrid_regime_exceeds_tail_budget",
        "numerical_diagnostics",
    }
)


@dataclass(frozen=True)
class FmmOccupancyVerifier:
    """Trusted non-asymptotic experiment with no repository code execution."""

    name: str = "fmm_occupancy"
    version: str = "0.1.0"
    default_experiment: str = "independent_occupancy_regimes"
    artifact_suffix: str = ".fmm.json"
    evidence_kind: str = "computational_experiment"
    environment_packages: tuple[str, ...] = ()

    def validate(
        self, experiment: str, request: dict[str, Any], assertions: list[str]
    ) -> None:
        if experiment != self.default_experiment:
            raise ValueError(f"Unsupported FMM occupancy experiment: {experiment}")
        OccupancyRegimeRequest.from_mapping(request)
        unknown = sorted(set(assertions) - ASSERTIONS)
        if unknown:
            raise ValueError(f"Unsupported assertions: {', '.join(unknown)}")
        if not assertions:
            raise ValueError("At least one FMM occupancy assertion is required")

    def run(self, experiment: str, request: dict[str, Any]) -> dict[str, Any]:
        self.validate(experiment, request, sorted(ASSERTIONS))
        return run_occupancy_regime_experiment(request)

    def source_paths(self) -> list[Path]:
        return sorted(Path(__file__).parent.glob("*.py"))


plugin = FmmOccupancyVerifier()
