"""Tests for optional advisory reviewers and their trust boundary."""

import json
import subprocess
from pathlib import Path

import pytest

import gitscience.review as review_module
from gitscience.cli import main
from gitscience.repository import GitScienceRepository
from gitscience.review import ReviewError, review_claim
from gitscience.verification import verify_claim
from gitscience_kwant.plugin import KwantTransportVerifier
from gitscience_physics_intern.bridge import _extract_result
from gitscience_physics_intern.plugin import PhysicsInternReviewer


def _science_repo(tmp_path: Path) -> tuple[GitScienceRepository, str]:
    repo = GitScienceRepository.init(tmp_path / "science", "review-test")
    repo.git(["config", "user.email", "science@example.test"])
    repo.git(["config", "user.name", "Science Test"])
    repo.create_topic("Quantum transport", "QT")
    model_source = tmp_path / "model.yaml"
    model_source.write_text("name: Test model\nkind: tight_binding\n")
    repo.create_model("ribbon-v1", model_source)
    claim_source = tmp_path / "claim.yaml"
    claim_source.write_text(
        """title: Transmission symmetry
statement: Transmission is even under reversal of the twist.
topic: QT
model: ribbon-v1
scope: numerical_instance
verification:
  verifier: kwant_transport
  request:
    width: 4
    length: 8
    energy: 1.0
    tau: 0.1
  assertions:
    - transmission_even_in_tau
    - numerical_diagnostics
"""
    )
    claim = repo.create_claim(claim_source)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Propose claim"])
    return repo, claim["id"]


def _fake_verification_result():
    return {
        "schema_version": "kwant-transport-v1",
        "claims": {
            "transmission_even_in_tau": {"passes": True, "absolute": 1e-12}
        },
        "diagnostics": {
            "plus_tau": {
                "hermitian": True,
                "unitary": True,
                "spin_decomposition_consistent": True,
                "lead_modes_matched": True,
            }
        },
    }


def _commit_evidence(repo: GitScienceRepository, evidence: dict) -> None:
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record evidence", "--", *paths])


class _FakeReviewer:
    name = "physics_intern"
    version = "test"
    environment_packages = ()

    def source_paths(self):
        return [Path(__file__)]

    def run(self, dossier, options):
        assert dossier["evidence"]
        return {
            "verdict": "VERIFIED",
            "summary": "The supplied evidence is internally consistent.",
            "details": "Advisory test result.",
            "sanity_checks": [],
        }


def test_review_requires_committed_integrity_valid_evidence(tmp_path, monkeypatch):
    repo, claim_id = _science_repo(tmp_path)
    monkeypatch.setattr(review_module, "get_reviewer", lambda name: _FakeReviewer())

    with pytest.raises(ReviewError, match="No integrity-valid committed evidence"):
        review_claim(repo, claim_id, "physics_intern")


def test_verified_review_is_versioned_but_does_not_change_status(tmp_path, monkeypatch):
    repo, claim_id = _science_repo(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _fake_verification_result(),
    )
    evidence = verify_claim(repo, claim_id)
    _commit_evidence(repo, evidence)
    status_before = repo.claim_status(claim_id)
    monkeypatch.setattr(review_module, "get_reviewer", lambda name: _FakeReviewer())

    review = review_claim(repo, claim_id, "physics_intern")

    assert review["id"] == "RV-000001"
    assert review["verdict"] == "VERIFIED"
    assert review["advisory"] is True
    assert review["affects_claim_status"] is False
    assert review["authentication"]["authenticated"] is False
    assert repo.claim_status(claim_id) == status_before == "corroborated"
    artifact = repo.root / review["artifact"]["path"]
    assert review["artifact"]["sha256"] == repo.sha256(artifact)


def test_cli_lists_advisory_review(tmp_path, monkeypatch, capsys):
    repo, claim_id = _science_repo(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _fake_verification_result(),
    )
    evidence = verify_claim(repo, claim_id)
    _commit_evidence(repo, evidence)
    monkeypatch.setattr(review_module, "get_reviewer", lambda name: _FakeReviewer())
    review_claim(repo, claim_id, "physics_intern")

    assert main(["-C", str(repo.root), "review", "list", "--claim", claim_id]) == 0
    assert f"RV-000001\t{claim_id}\tVERIFIED\tadvisory" in capsys.readouterr().out


def test_physics_intern_adapter_uses_bounded_subprocess(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps({"verdict": "INCONCLUSIVE", "summary": "Needs controls"})
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = PhysicsInternReviewer().run({"claim": {}}, {"timeout": 12})

    assert result["verdict"] == "INCONCLUSIVE"
    assert seen["kwargs"]["timeout"] == 12
    assert seen["kwargs"]["check"] is False
    assert "shell" not in seen["kwargs"]


def test_bridge_extracts_last_structured_verdict():
    text = 'analysis {"verdict":"REFUTED","summary":"first"} then '
    text += '```json\n{"verdict":"VERIFIED","summary":"final"}\n```'

    assert _extract_result(text)["summary"] == "final"
