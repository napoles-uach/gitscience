"""Schema-limited verifier for bundled Lean proofs."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROOFS = {
    "fmm_error_accumulation": {
        "file": "fmm_error_accumulation.lean",
        "assertions": {"local_error_bounds_accumulate"},
        "title": "Local error bounds accumulate",
        "summary": (
            "An abstract induction showing that declared local error bounds "
            "accumulate under the supplied ordered addition law."
        ),
        "theorem_name": "local_error_bounds_accumulate",
        "formal_statement": {
            "language": "lean4",
            "theorem_name": "local_error_bounds_accumulate",
            "declaration": """theorem local_error_bounds_accumulate
    {Error : Type}
    (budget : ErrorBudget Error)
    (cumulative stepError : Nat -> Error)
    (initial : budget.le (cumulative 0) budget.zero)
    (step : forall n,
      budget.le (cumulative (n + 1))
        (budget.add (cumulative n) (stepError n))) :
    forall steps,
      budget.le (cumulative steps) (accumulatedError budget stepError steps)""",
        },
    },
    "twist_transport_symmetry": {
        "file": "twist_transport_symmetry.lean",
        "assertions": {"transport_symmetry_implies_even_transmission"},
        "title": "Scattering covariance implies even transmission",
        "summary": (
            "An abstract implication from scattering covariance and transmission "
            "invariance to equality under twist reversal."
        ),
        "theorem_name": "transport_symmetry_implies_even_transmission",
        "formal_statement": {
            "language": "lean4",
            "theorem_name": "transport_symmetry_implies_even_transmission",
            "declaration": """theorem transport_symmetry_implies_even_transmission
    {Twist Scattering Value : Type}
    (system : TransportSymmetry Twist Scattering Value)
    (tau : Twist) :
    system.transmission (system.scattering (system.reverse tau)) =
      system.transmission (system.scattering tau)""",
        },
    },
}


@dataclass(frozen=True)
class LeanFormalVerifier:
    """Run only formal proofs distributed with this trusted adapter."""

    name: str = "lean_formal"
    version: str = "0.1.0"
    default_experiment: str = "trusted_proof"
    artifact_suffix: str = ".lean.json"
    evidence_kind: str = "formal_proof"
    environment_packages: tuple[str, ...] = ()

    @staticmethod
    def _proof(request: dict[str, Any]) -> tuple[str, Path, set[str]]:
        if set(request) != {"proof"} or not isinstance(request.get("proof"), str):
            raise ValueError("Lean request must contain only a string proof name")
        proof_name = request["proof"]
        definition = PROOFS.get(proof_name)
        if definition is None:
            raise ValueError(f"Unknown trusted Lean proof: {proof_name}")
        path = Path(__file__).parent / "proofs" / definition["file"]
        return proof_name, path, definition["assertions"]

    def validate(
        self, experiment: str, request: dict[str, Any], assertions: list[str]
    ) -> None:
        if experiment != self.default_experiment:
            raise ValueError(f"Unsupported Lean experiment: {experiment}")
        _, _, allowed = self._proof(request)
        unknown = sorted(set(assertions) - allowed)
        if unknown:
            raise ValueError(f"Unsupported assertions: {', '.join(unknown)}")
        if not assertions:
            raise ValueError("At least one Lean assertion is required")

    def run(self, experiment: str, request: dict[str, Any]) -> dict[str, Any]:
        proof_name, proof_path, allowed = self._proof(request)
        self.validate(experiment, request, sorted(allowed))
        executable = shutil.which("lean")
        if executable is None:
            raise RuntimeError(
                "Lean is not installed or is not on PATH. Install Lean through elan."
            )
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        process = subprocess.run(
            [executable, str(proof_path)],
            cwd=proof_path.parent,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        elaborated = process.returncode == 0
        # Failure to elaborate establishes neither the assertion nor its negation.
        # A refutation would require a separate trusted proof of the negated claim.
        passed = True if elaborated else None
        detail = {
            "passes": passed,
            "proof": proof_name,
            "source": proof_path.name,
            "exit_code": process.returncode,
            "stdout": process.stdout[-10_000:],
            "stderr": process.stderr[-10_000:],
        }
        return {
            "schema_version": "gitscience-lean-v1",
            "lean_version": (version.stdout or version.stderr).strip(),
            "trusted_bundled_source": True,
            "claims": {assertion: detail for assertion in sorted(allowed)},
            "diagnostics": {
                "lean_invocation_succeeded": version.returncode == 0,
                "elaboration_succeeded": elaborated,
                "assertion_established": passed is True,
            },
        }

    def source_paths(self) -> list[Path]:
        package = Path(__file__).parent
        return sorted((*package.glob("*.py"), *(package / "proofs").glob("*.lean")))

    def formalization_catalog(self) -> list[dict[str, Any]]:
        """Describe trusted proof contracts an agent may request."""
        return [
            {
                "title": definition["title"],
                "summary": definition["summary"],
                "theorem_name": definition["theorem_name"],
                "formal_statement": definition["formal_statement"],
                "verification": {
                    "verifier": self.name,
                    "experiment": self.default_experiment,
                    "request": {"proof": proof_name},
                    "assertions": sorted(definition["assertions"]),
                },
            }
            for proof_name, definition in sorted(PROOFS.items())
        ]


plugin = LeanFormalVerifier()
