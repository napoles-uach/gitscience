"""Tests for typed claim graphs and the trusted Lean adapter."""

import subprocess
from pathlib import Path

import pytest

from gitscience.cli import main
from gitscience.repository import GitScienceRepository, RepositoryError
from gitscience.verification import VerificationError, verify_claim
from gitscience_lean.plugin import LeanFormalVerifier


def _repo(tmp_path: Path) -> GitScienceRepository:
    repo = GitScienceRepository.init(tmp_path / "science", "formal-graph")
    repo.git(["config", "user.email", "formal@example.test"])
    repo.git(["config", "user.name", "Formal Test"])
    repo.create_topic("Quantum transport", "QT")
    model = tmp_path / "model.yaml"
    model.write_text("name: Formal test model\nkind: tight_binding\n")
    repo.create_model("formal-v1", model)
    return repo


def _node(tmp_path: Path, name: str, kind: str, dependencies=()) -> Path:
    dependencies_yaml = "\n".join(f"  - {item}" for item in dependencies)
    if not dependencies_yaml:
        dependencies_yaml = "  []"
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        f"""kind: {kind}
title: {name}
statement:
  natural_language: A precise scientific statement for {name}.
  latex: |
    T(-\\tau)=T(\\tau).
topic: QT
model: formal-v1
scope: general
depends_on:
{dependencies_yaml}
"""
    )
    return path


def test_typed_claims_form_a_dependency_graph(tmp_path):
    repo = _repo(tmp_path)
    definition = repo.create_claim(_node(tmp_path, "definition", "definition"))
    lemma = repo.create_claim(
        _node(tmp_path, "lemma", "lemma", [definition["id"]])
    )

    graph = repo.claim_graph()

    assert definition["kind"] == "definition"
    assert repo.claim_status(definition["id"]) == "declared"
    assert lemma["statement"]["latex"].strip() == r"T(-\tau)=T(\tau)."
    assert graph["edges"] == [{"from": definition["id"], "to": lemma["id"]}]


def test_claim_rejects_dangling_dependency(tmp_path):
    repo = _repo(tmp_path)

    with pytest.raises(RepositoryError, match="Unknown claim"):
        repo.create_claim(_node(tmp_path, "lemma", "lemma", ["GS-QT-9999"]))


def test_unverified_definition_cannot_be_executed(tmp_path):
    repo = _repo(tmp_path)
    definition = repo.create_claim(_node(tmp_path, "definition", "definition"))
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Add definition"])

    with pytest.raises(VerificationError, match="has no computational verifier"):
        verify_claim(repo, definition["id"])


def test_cli_renders_argument_dependencies(tmp_path, capsys):
    repo = _repo(tmp_path)
    definition = repo.create_claim(_node(tmp_path, "definition", "definition"))
    lemma = repo.create_claim(
        _node(tmp_path, "lemma", "lemma", [definition["id"]])
    )

    assert main(["-C", str(repo.root), "claim", "graph"]) == 0
    output = capsys.readouterr().out
    assert f"{definition['id']} [definition, declared]" in output
    assert f"depends on: {definition['id']}" in output
    assert lemma["id"] in output


def test_lean_plugin_rejects_repository_supplied_proof():
    verifier = LeanFormalVerifier()

    with pytest.raises(ValueError, match="Unknown trusted Lean proof"):
        verifier.validate(
            "trusted_proof",
            {"proof": "../../untrusted"},
            ["transport_symmetry_implies_even_transmission"],
        )


def test_lean_plugin_runs_bundled_proof(monkeypatch):
    verifier = LeanFormalVerifier()

    monkeypatch.setattr("gitscience_lean.plugin.shutil.which", lambda name: "/bin/lean")

    def fake_run(command, **kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "Lean 4.test\n", "")
        assert command[-1].endswith("twist_transport_symmetry.lean")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("gitscience_lean.plugin.subprocess.run", fake_run)
    result = verifier.run(
        "trusted_proof", {"proof": "twist_transport_symmetry"}
    )

    claim = result["claims"]["transport_symmetry_implies_even_transmission"]
    assert claim["passes"] is True
    assert result["trusted_bundled_source"] is True
    assert result["lean_version"] == "Lean 4.test"
    assert verifier.evidence_kind == "formal_proof"


def test_lean_elaboration_failure_is_inconclusive_not_contradictory(monkeypatch):
    verifier = LeanFormalVerifier()
    monkeypatch.setattr("gitscience_lean.plugin.shutil.which", lambda name: "/bin/lean")

    def fake_run(command, **kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "Lean 4.test\n", "")
        return subprocess.CompletedProcess(command, 1, "", "type mismatch")

    monkeypatch.setattr("gitscience_lean.plugin.subprocess.run", fake_run)
    result = verifier.run(
        "trusted_proof", {"proof": "twist_transport_symmetry"}
    )

    claim = result["claims"]["transport_symmetry_implies_even_transmission"]
    assert claim["passes"] is None
    assert result["diagnostics"]["elaboration_succeeded"] is False
    assert result["diagnostics"]["assertion_established"] is False


def test_lean_plugin_selects_fmm_accumulation_proof(monkeypatch):
    verifier = LeanFormalVerifier()
    monkeypatch.setattr("gitscience_lean.plugin.shutil.which", lambda name: "/bin/lean")

    def fake_run(command, **kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "Lean 4.test\n", "")
        assert command[-1].endswith("fmm_error_accumulation.lean")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("gitscience_lean.plugin.subprocess.run", fake_run)
    result = verifier.run("trusted_proof", {"proof": "fmm_error_accumulation"})

    claim = result["claims"]["local_error_bounds_accumulate"]
    assert claim["passes"] is True
    assert claim["proof"] == "fmm_error_accumulation"


def test_dependency_change_makes_formal_result_stale(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    definition = repo.create_claim(_node(tmp_path, "definition", "definition"))
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Define model"])

    assumption = repo.create_claim(
        _node(tmp_path, "assumption", "assumption", [definition["id"]])
    )
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Declare assumption"])

    lemma_source = _node(
        tmp_path, "formal-lemma", "lemma", [definition["id"], assumption["id"]]
    )
    lemma_source.write_text(
        lemma_source.read_text()
        + """verification:
  verifier: lean_formal
  experiment: trusted_proof
  request:
    proof: twist_transport_symmetry
  assertions:
    - transport_symmetry_implies_even_transmission
"""
    )
    verifier = LeanFormalVerifier()
    monkeypatch.setattr("gitscience.repository.get_verifier", lambda name: verifier)
    monkeypatch.setattr("gitscience.verification.get_verifier", lambda name: verifier)
    monkeypatch.setattr(
        LeanFormalVerifier,
        "run",
        lambda self, experiment, request: {
            "claims": {
                "transport_symmetry_implies_even_transmission": {
                    "passes": True,
                    "proof": "twist_transport_symmetry",
                }
            },
            "diagnostics": {"elaboration_succeeded": True},
        },
    )
    lemma = repo.create_claim(lemma_source)
    assert {item["id"] for item in lemma["dependency_revisions"]} == {
        definition["id"],
        assumption["id"],
    }
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "State conditional lemma"])

    evidence = verify_claim(repo, lemma["id"])
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Check lemma", "--", *paths])
    assert evidence["dependencies"] == lemma["dependency_revisions"]
    assert repo.claim_status(lemma["id"]) == "conditional_proven"

    corollary = repo.create_claim(
        _node(tmp_path, "corollary", "corollary", [lemma["id"]])
    )
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Add dependent corollary"])

    assumption_path = repo.claim_path(assumption["id"])
    assumption_path.write_text(assumption_path.read_text() + "notes: revised\n")
    repo.git(["add", assumption_path.relative_to(repo.root).as_posix()])
    repo.git(["commit", "-m", "Revise physical assumption"])

    assert repo.claim_status(lemma["id"]) == "stale"
    assert repo.claim_status(corollary["id"]) == "stale"
    with pytest.raises(VerificationError, match="changed since its locked revision"):
        verify_claim(repo, lemma["id"])

    repo.lock_dependencies(lemma["id"])
    repo.git(["add", repo.claim_path(lemma["id"]).relative_to(repo.root).as_posix()])
    repo.git(["commit", "-m", "Relock lemma dependencies"])
    assert repo.claim_status(lemma["id"]) == "conditional"
    assert repo.claim_status(corollary["id"]) == "stale"
