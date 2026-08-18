"""Tests for agent-proposed, human-approved formal verification."""

from __future__ import annotations

from pathlib import Path

import pytest

import gitscience.formalization as formalization_module
import gitscience.repository as repository_module
import gitscience.verification as verification_module
from gitscience.formalization import (
    FormalizationError,
    approve_formalization,
    create_formalization,
    request_formalization,
    verify_formalization,
)
from gitscience.repository import GitScienceRepository
from gitscience.state import compile_claim_state
from gitscience_lean.plugin import LeanFormalVerifier


def _repo(tmp_path: Path) -> tuple[GitScienceRepository, str]:
    repo = GitScienceRepository.init(tmp_path / "science", "formalization-test")
    repo.git(["config", "user.name", "Formalization Test"])
    repo.git(["config", "user.email", "formalization@example.test"])
    repo.create_topic("Quantum transport", "QT")
    model = tmp_path / "model.yaml"
    model.write_text("name: Formal model\nkind: tight_binding\n")
    repo.create_model("formal-v1", model)
    claim = tmp_path / "claim.yaml"
    claim.write_text(
        """kind: lemma
title: Conditional transport symmetry
statement:
  natural_language: Covariance implies even transmission.
  latex: T(E,-\\tau)=T(E,\\tau)
topic: QT
model: formal-v1
scope: general
"""
    )
    record = repo.create_claim(claim)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "State claim"])
    return repo, record["id"]


def _proposal() -> dict:
    return {
        "summary": "Formalize the abstract covariance implication.",
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
        "semantic_mapping": [
            {
                "source": "Covariance implies even transmission.",
                "target": "transport_symmetry_implies_even_transmission",
                "status": "partial",
            }
        ],
        "assumptions": ["Scattering covariance holds."],
        "unformalized": ["The Hamiltonian satisfies covariance."],
        "scientific_grounding": {
            "status": "partial",
            "rationale": "The model-to-theorem correspondence remains open.",
        },
        "verification": {
            "verifier": "lean_formal",
            "experiment": "trusted_proof",
            "request": {"proof": "twist_transport_symmetry"},
            "assertions": ["transport_symmetry_implies_even_transmission"],
        },
    }


def _patch_lean(monkeypatch) -> LeanFormalVerifier:
    verifier = LeanFormalVerifier()
    monkeypatch.setattr(repository_module, "get_verifier", lambda name: verifier)
    monkeypatch.setattr(formalization_module, "get_verifier", lambda name: verifier)
    monkeypatch.setattr(verification_module, "get_verifier", lambda name: verifier)
    monkeypatch.setattr(
        LeanFormalVerifier,
        "run",
        lambda self, experiment, request: {
            "schema_version": "gitscience-lean-v1",
            "claims": {
                "transport_symmetry_implies_even_transmission": {
                    "passes": True,
                    "proof": "twist_transport_symmetry",
                    "source": "twist_transport_symmetry.lean",
                }
            },
            "diagnostics": {"elaboration_succeeded": True},
        },
    )
    return verifier


def _commit_formalization(repo: GitScienceRepository, message: str) -> None:
    repo.git(["add", "-A", "--", ".gitscience", "formalizations"])
    repo.git(["commit", "-m", message, "--", ".gitscience", "formalizations"])


def _commit_evidence(repo: GitScienceRepository, evidence: dict) -> None:
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record formal evidence", "--", *paths])


def test_human_approval_gates_lean_and_preserves_partial_grounding(
    tmp_path, monkeypatch
):
    repo, claim_id = _repo(tmp_path)
    _patch_lean(monkeypatch)
    formalization = create_formalization(
        repo,
        claim_id,
        _proposal(),
        {"kind": "human", "name": "Researcher"},
    )
    _commit_formalization(repo, "Propose formalization")

    draft_state = compile_claim_state(repo, claim_id)
    assert draft_state["status"]["dimensions"]["formalization"] == "draft"
    assert any(
        item["type"] == "formalization_approval"
        for item in draft_state["obligations"]
    )
    with pytest.raises(FormalizationError, match="approval is required"):
        verify_formalization(repo, formalization["id"])

    approve_formalization(repo, formalization["id"])
    _commit_formalization(repo, "Approve formalization")
    evidence = verify_formalization(repo, formalization["id"])
    assert evidence["formalization"]["semantic_approval"] == "accepted"
    _commit_evidence(repo, evidence)

    state = compile_claim_state(repo, claim_id)
    assert state["status"]["derived"] == "conditional_proven"
    assert state["status"]["dimensions"]["logical"] == "proven"
    assert state["status"]["dimensions"]["formalization"] == "human_approved"
    assert state["status"]["dimensions"]["scientific_grounding"] == "partial"
    assert state["formalizations"][0]["semantic_approval"]["status"] == "accepted"
    assert any(
        item["type"] == "scientific_grounding" for item in state["obligations"]
    )


def test_statement_change_invalidates_approval(tmp_path, monkeypatch):
    repo, claim_id = _repo(tmp_path)
    _patch_lean(monkeypatch)
    formalization = create_formalization(
        repo,
        claim_id,
        _proposal(),
        {"kind": "human", "name": "Researcher"},
    )
    _commit_formalization(repo, "Propose formalization")
    approved = approve_formalization(repo, formalization["id"])
    _commit_formalization(repo, "Approve formalization")

    approved["formal_statement"]["declaration"] = "theorem easier_statement : True"
    repo.write_yaml(repo.formalization_path(formalization["id"]), approved)

    with pytest.raises(FormalizationError, match="Invalid formalization"):
        verify_formalization(repo, formalization["id"])


def test_statement_cannot_borrow_an_unrelated_trusted_contract(
    tmp_path, monkeypatch
):
    repo, claim_id = _repo(tmp_path)
    _patch_lean(monkeypatch)
    proposal = _proposal()
    proposal["formal_statement"]["declaration"] = "theorem easier_statement : True"

    with pytest.raises(FormalizationError, match="exactly match"):
        create_formalization(
            repo,
            claim_id,
            proposal,
            {"kind": "human", "name": "Researcher"},
        )


class _FakeFormalizer:
    name = "physics_intern"
    version = "test"
    environment_packages = ()

    def source_paths(self):
        return [Path(__file__)]

    def run(self, dossier, options):
        assert dossier["policy"]["human_semantic_approval_required"] is True
        assert dossier["available_formal_verifications"]
        return _proposal()


def test_llm_can_request_but_not_approve_formalization(tmp_path, monkeypatch):
    repo, claim_id = _repo(tmp_path)
    _patch_lean(monkeypatch)
    monkeypatch.setattr(
        formalization_module, "get_formalizer", lambda name: _FakeFormalizer()
    )

    record = request_formalization(
        repo, claim_id, "physics_intern", {"model": "test-model"}
    )

    assert record["status"] == "draft"
    assert record["proposer"]["kind"] == "llm"
    assert record["proposer"]["model"] == "test-model"
    assert record["semantic_approval"] == {"status": "pending"}
