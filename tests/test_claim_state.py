"""Tests for the canonical, LLM-readable claim state."""

import json
from pathlib import Path

from gitscience.cli import main
from gitscience.repository import GitScienceRepository
from gitscience.state import compile_claim_state
from gitscience.verification import verify_claim
from gitscience_kwant.plugin import KwantTransportVerifier


def _repo_with_conditional_claim(
    tmp_path: Path,
) -> tuple[GitScienceRepository, str, str]:
    repo = GitScienceRepository.init(tmp_path / "science", "claim-state")
    repo.git(["config", "user.email", "state@example.test"])
    repo.git(["config", "user.name", "State Test"])
    repo.create_topic("Quantum transport", "QT")
    model_source = tmp_path / "model.yaml"
    model_source.write_text("name: Twisted ribbon\nkind: tight_binding\n")
    repo.create_model("ribbon-v1", model_source)

    assumption_source = tmp_path / "assumption.yaml"
    assumption_source.write_text(
        """kind: assumption
title: Covariant twist model
statement: Reversing twist is represented without changing the leads.
topic: QT
model: ribbon-v1
scope: general
"""
    )
    assumption = repo.create_claim(assumption_source)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Declare model and assumption"])

    claim_source = tmp_path / "claim.yaml"
    claim_source.write_text(
        f"""kind: numerical_proposition
title: Transmission symmetry
statement:
  natural_language: Transmission is even under reversal of the twist.
  latex: T(-\\tau)=T(\\tau).
topic: QT
model: ribbon-v1
scope: numerical_instance
depends_on:
  - {assumption['id']}
conditions:
  - Fixed width, length, energy, and lead construction.
limitations:
  - This finite sweep does not establish all energies or geometries.
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
    repo.git(["commit", "-m", "State conditional numerical claim"])
    return repo, assumption["id"], claim["id"]


def _result(passes: bool = True) -> dict:
    return {
        "schema_version": "kwant-transport-v1",
        "claims": {
            "transmission_even_in_tau": {
                "passes": passes,
                "absolute": 1e-12 if passes else 0.2,
            }
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


def _record_evidence(repo: GitScienceRepository, claim_id: str) -> dict:
    evidence = verify_claim(repo, claim_id)
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record evidence", "--", *paths])
    return evidence


def test_state_exposes_conditional_support_and_scope(tmp_path, monkeypatch):
    repo, assumption_id, claim_id = _repo_with_conditional_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier, "run", lambda self, experiment, request: _result()
    )
    _record_evidence(repo, claim_id)

    state = compile_claim_state(repo, claim_id)

    assert state == compile_claim_state(repo, claim_id)
    assert state["schema_version"] == "gitscience-claim-state-v1"
    assert state["status"]["derived"] == "conditional_corroborated"
    assert state["status"]["dimensions"] == {
        "logical": "not_applicable",
        "computational": "corroborated",
        "dependencies": "conditional",
        "provenance": "unauthenticated",
        "review": "unreviewed",
        "revision": "committed",
    }
    assert state["dependency_closure"]["nodes"][0]["id"] == assumption_id
    assert (
        state["dependency_closure"]["nodes"][0]["dependency_report"]["conditional"]
        is False
    )
    assert state["evidence"][0]["assertions"][0]["outcome"] == "satisfied"
    assert state["evidence"][0]["assertions"][0]["supports_claim"] is True
    obligation_types = {item["type"] for item in state["obligations"]}
    assert "unresolved_assumption" in obligation_types
    assert "scope_limitation" in obligation_types
    assert "unauthenticated_evidence" in obligation_types
    json.dumps(state)


def test_failed_assertion_is_not_hidden_by_boolean_wording(tmp_path, monkeypatch):
    repo, _, claim_id = _repo_with_conditional_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: _result(passes=False),
    )
    _record_evidence(repo, claim_id)

    state = compile_claim_state(repo, claim_id)

    assertion = state["evidence"][0]["assertions"][0]
    assert state["status"]["derived"] == "contested"
    assert state["status"]["dimensions"]["computational"] == "contradicted"
    assert assertion["outcome"] == "failed"
    assert assertion["supports_claim"] is False


def test_claim_edit_excludes_evidence_for_older_revision(tmp_path, monkeypatch):
    repo, _, claim_id = _repo_with_conditional_claim(tmp_path)
    monkeypatch.setattr(
        KwantTransportVerifier, "run", lambda self, experiment, request: _result()
    )
    _record_evidence(repo, claim_id)
    claim_path = repo.claim_path(claim_id)
    claim_path.write_text(claim_path.read_text() + "notes: broadened interpretation\n")

    state = compile_claim_state(repo, claim_id)

    assert state["claim"]["revision"]["state"] == "uncommitted"
    assert state["evidence"] == []
    assert state["status"]["dimensions"]["computational"] == "untested"
    assert any(
        item["type"] == "no_current_evidence" for item in state["obligations"]
    )


def test_cli_emits_machine_and_human_views(tmp_path, capsys):
    repo, _, claim_id = _repo_with_conditional_claim(tmp_path)

    assert (
        main(["-C", str(repo.root), "claim", "state", claim_id, "--json"]) == 0
    )
    state = json.loads(capsys.readouterr().out)
    assert state["claim"]["id"] == claim_id
    assert state["status"]["derived"] == "conditional"

    assert main(["-C", str(repo.root), "claim", "explain", claim_id]) == 0
    output = capsys.readouterr().out
    assert f"{claim_id} - Transmission symmetry" in output
    assert "computational: untested" in output
    assert "No integrity-valid evidence targets the current claim revision." in output


def test_uncommitted_forged_review_is_excluded_from_state(tmp_path):
    repo, _, claim_id = _repo_with_conditional_claim(tmp_path)
    claim_digest = repo.sha256(repo.claim_path(claim_id))
    artifact = repo.root / "review-artifacts" / "RV-999999.json"
    artifact.write_text('{"verdict":"VERIFIED","summary":"trust me"}\n')
    review = {
        "schema_version": "gitscience-review-v1",
        "id": "RV-999999",
        "advisory": True,
        "affects_claim_status": False,
        "claim": {"id": claim_id, "sha256": claim_digest},
        "artifact": {
            "path": artifact.relative_to(repo.root).as_posix(),
            "sha256": repo.sha256(artifact),
        },
    }
    repo.review_path("RV-999999").write_text(json.dumps(review))

    state = compile_claim_state(repo, claim_id)

    assert state["reviews"] == []
    assert state["status"]["dimensions"]["review"] == "unreviewed"
