"""Adversarial tests for evidence that was not produced by a trusted run."""

import hashlib
import json

from gitscience.cli import main
from gitscience.repository import GitScienceRepository
from gitscience.verification import verify_claim
from gitscience_kwant.plugin import KwantTransportVerifier


def _repository_with_claim(tmp_path):
    repo = GitScienceRepository.init(tmp_path / "science", "adversarial-test")
    repo.git(["config", "user.email", "audit@example.test"])
    repo.git(["config", "user.name", "Adversarial Test"])
    repo.create_topic("Quantum transport", "QT")
    model = tmp_path / "model.yaml"
    model.write_text("name: Audit model\nkind: tight_binding\n")
    repo.create_model("helicoidal-v1", model)
    claim = tmp_path / "claim.yaml"
    claim.write_text(
        """title: Audit claim
statement: Transmission is even under twist reversal.
topic: QT
model: helicoidal-v1
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
    created = repo.create_claim(claim)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Propose audit claim"])
    return repo, created


def _result():
    return {
        "schema_version": "kwant-transport-v1",
        "claims": {"transmission_even_in_tau": {"passes": True, "absolute": 0.0}},
        "diagnostics": {
            "plus_tau": {
                "hermitian": True,
                "unitary": True,
                "spin_decomposition_consistent": True,
                "lead_modes_matched": True,
            }
        },
    }


def _commit_evidence(repo, evidence):
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record audit evidence", "--", *paths])


def test_uncommitted_minimal_fake_cannot_corroborate(tmp_path):
    repo, claim = _repository_with_claim(tmp_path)
    digest = hashlib.sha256(repo.claim_path(claim["id"]).read_bytes()).hexdigest()
    fake = {
        "id": "EV-999999",
        "classification": "corroborating",
        "claim": {"id": claim["id"], "sha256": digest},
    }
    repo.evidence_path("EV-999999").write_text(json.dumps(fake) + "\n")

    report = repo.audit_evidence(repo.evidence_path("EV-999999"))

    assert report["valid"] is False
    assert repo.claim_status(claim["id"]) == "proposed"
    assert any("not committed" in error for error in report["errors"])


def test_tampered_artifact_invalidates_committed_evidence(tmp_path, monkeypatch):
    repo, claim = _repository_with_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _result(),
    )
    evidence = verify_claim(repo, claim["id"])
    _commit_evidence(repo, evidence)
    assert repo.claim_status(claim["id"]) == "corroborated"

    artifact = repo.root / evidence["artifact"]["path"]
    artifact.write_text('{"fabricated": true}\n')
    report = repo.audit_evidence(repo.evidence_path(evidence["id"]))

    assert report["valid"] is False
    assert repo.claim_status(claim["id"]) == "proposed"
    assert any("artifact SHA-256" in error for error in report["errors"])


def test_audit_command_returns_failure_for_forged_evidence(tmp_path, capsys):
    repo, claim = _repository_with_claim(tmp_path)
    repo.evidence_path("EV-999999").write_text(
        json.dumps(
            {
                "id": "EV-999999",
                "classification": "corroborating",
                "claim": {"id": claim["id"]},
            }
        )
        + "\n"
    )

    assert main(["-C", str(repo.root), "audit"]) == 1
    output = capsys.readouterr().out
    assert "EV-999999\tINVALID" in output
    assert "error:" in output


def test_unsigned_valid_evidence_fails_strict_authentication_policy(
    tmp_path, monkeypatch, capsys
):
    repo, claim = _repository_with_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _result(),
    )
    evidence = verify_claim(repo, claim["id"])
    _commit_evidence(repo, evidence)

    assert main(["-C", str(repo.root), "audit", "--claim", claim["id"]]) == 0
    assert "integrity-valid" in capsys.readouterr().out
    assert (
        main(
            [
                "-C",
                str(repo.root),
                "audit",
                "--claim",
                claim["id"],
                "--require-authenticated",
            ]
        )
        == 1
    )
    assert "not cryptographically authenticated" in capsys.readouterr().out


def test_self_declared_authentication_is_rejected(tmp_path, monkeypatch):
    repo, claim = _repository_with_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _result(),
    )
    evidence = verify_claim(repo, claim["id"])
    evidence["authentication"] = {
        "method": "trust-me",
        "authenticated": True,
    }
    repo.evidence_path(evidence["id"]).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    _commit_evidence(repo, evidence)

    report = repo.audit_evidence(repo.evidence_path(evidence["id"]))

    assert report["valid"] is False
    assert any("unverifiable authentication" in error for error in report["errors"])
    assert repo.claim_status(claim["id"]) == "proposed"
