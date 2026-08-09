"""Optional end-to-end GitScience verification with a real Kwant solver."""

import json
from pathlib import Path

import pytest

pytest.importorskip("kwant")

from gitscience.repository import GitScienceRepository
from gitscience.verification import verify_claim


def _commit_evidence(repo, evidence):
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record Kwant evidence", "--", *paths])


def test_gitscience_records_real_kwant_attestation(tmp_path):
    repo = GitScienceRepository.init(tmp_path / "science", "kwant-integration")
    repo.git(["config", "user.email", "kwant@example.test"])
    repo.git(["config", "user.name", "Kwant Integration"])
    repo.create_topic("Quantum transport", "QT")

    model_source = tmp_path / "model.yaml"
    model_source.write_text("name: Effective helicoidal ribbon\nkind: tight_binding\n")
    repo.create_model("helicoidal-v1", model_source)

    claim_source = tmp_path / "claim.yaml"
    claim_source.write_text(
        """title: Transmission parity reference
statement: T(+tau) equals T(-tau) at the declared point.
topic: QT
model: helicoidal-v1
scope: numerical_instance
verification:
  verifier: kwant_transport
  request:
    width: 8
    length: 24
    energy: 1.0
    tau: 0.08
    hopping: 1.0
    soc: 0.1
    onsite: 0.0
  assertions:
    - transmission_even_in_tau
    - numerical_diagnostics
"""
    )
    claim = repo.create_claim(claim_source)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Propose reference claim"])

    evidence = verify_claim(repo, claim["id"])
    _commit_evidence(repo, evidence)

    assert evidence["classification"] == "corroborating"
    assert evidence["environment"]["packages"]["kwant"] == "1.5.0"
    assert repo.claim_status(claim["id"]) == "corroborated"
    assert Path(repo.root / evidence["artifact"]["path"]).exists()


def test_gitscience_records_real_small_twist_claim(tmp_path):
    repo = GitScienceRepository.init(tmp_path / "scaling", "kwant-scaling")
    repo.git(["config", "user.email", "kwant@example.test"])
    repo.git(["config", "user.name", "Kwant Integration"])
    repo.create_topic("Quantum transport", "QT")
    model_source = tmp_path / "scaling-model.yaml"
    model_source.write_text("name: Effective helicoidal ribbon\nkind: tight_binding\n")
    repo.create_model("helicoidal-v1", model_source)
    claim_source = tmp_path / "scaling-claim.yaml"
    claim_source.write_text(
        """title: Small-twist polarization scaling
statement: The odd x-spin polarization is approximately linear.
topic: QT
model: helicoidal-v1
scope: numerical_instance
verification:
  verifier: kwant_transport
  experiment: small_twist_scaling
  request:
    width: 8
    length: 24
    energy: 1.0
    tau_values: [0.0, 0.01, 0.02, 0.03, 0.04]
    hopping: 1.0
    soc: 0.1
    onsite: 0.0
    linearity_tolerance: 0.06
    quadratic_tolerance: 0.05
  assertions:
    - polarization_linear_in_small_twist
    - numerical_diagnostics
"""
    )
    claim = repo.create_claim(claim_source)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Propose scaling claim"])

    evidence = verify_claim(repo, claim["id"])
    artifact = repo.root / evidence["artifact"]["path"]
    result = json.loads(artifact.read_text())

    assert evidence["classification"] == "corroborating"
    scaling = result["claims"]["polarization_linear_in_small_twist"]
    assert scaling["slope"] == pytest.approx(0.0466542043, rel=1e-7)
    assert scaling["relative_max_residual"] < 0.06
