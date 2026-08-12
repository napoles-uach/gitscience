"""Tests for study narratives and public registry snapshots."""

import json
from pathlib import Path

import pytest

from gitscience.cli import main
from gitscience.registry import compile_registry, merge_registry_snapshots
from gitscience.repository import GitScienceRepository, RepositoryError
from gitscience.state import compile_claim_state, explain_claim_state


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def _repository(tmp_path: Path) -> GitScienceRepository:
    repo = GitScienceRepository.init(tmp_path / "science", "Narrative test")
    repo.git(["config", "user.email", "science@example.test"])
    repo.git(["config", "user.name", "Science Test"])
    repo.create_topic("Quantum transport", "QT")
    repo.create_model(
        "ribbon-v1",
        _write(tmp_path / "model.yaml", "name: Ribbon\nkind: tight_binding\n"),
    )
    repo.create_study(
        "twisted-ribbon",
        _write(
            tmp_path / "study.yaml",
            """name: Twisted ribbon transport
research_question: Is transmission even under twist reversal?
approach_summary: Separate assumptions, proof, and numerical evidence.
resolution_summary: One finite instance is corroborated conditionally.
""",
        ),
    )
    return repo


def _claim(tmp_path: Path, title: str, role: str) -> Path:
    slug = title.lower().replace(" ", "-")
    return _write(
        tmp_path / f"{slug}.yaml",
        f"""title: {title}
statement: A technical statement for {title}.
topic: QT
model: ribbon-v1
study: twisted-ribbon
role: {role}
question: What does {title} establish?
plain_language_conclusion: It records the {role} for this study.
scope_summary: The declared model and scope only.
remaining_uncertainty: Independent validation remains open.
scope: general
""",
    )


def test_study_narrative_is_versioned_in_claim_state(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim(tmp_path, "Main result", "main_result"))
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Record narrative study"])

    state = compile_claim_state(repo, claim["id"])

    assert state["study"]["id"] == "twisted-ribbon"
    assert state["study"]["revision"]["state"] == "committed"
    assert state["claim"]["role"] == "main_result"
    assert state["narrative"]["research_question"].startswith("Is transmission")
    assert "Resolution:" in explain_claim_state(state)


def test_registry_discloses_partial_coverage_and_full_claim_index(tmp_path):
    repo = _repository(tmp_path)
    supporting = repo.create_claim(
        _claim(tmp_path, "Supporting result", "supporting_result")
    )
    headline = repo.create_claim(_claim(tmp_path, "Main result", "main_result"))
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Record claim chain"])

    registry = compile_registry(repo, [headline["id"]])
    study = registry["studies"][0]

    assert registry["schema_version"] == "gitscience-observatory-v1"
    assert registry["sources"][0]["repository_name"] == "Narrative test"
    assert study["coverage"] == {"shown": 1, "total": 2, "is_complete": False}
    assert study["headline_claim_ids"] == [headline["id"]]
    assert [item["id"] for item in study["claim_index"]] == [
        supporting["id"],
        headline["id"],
    ]
    assert len(registry["claims"]) == 1


def test_registry_export_cli_writes_canonical_json(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim(tmp_path, "Main result", "main_result"))
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Record exportable claim"])
    output = tmp_path / "registry.json"

    assert (
        main(
            [
                "-C",
                str(repo.root),
                "registry",
                "export",
                "--claim",
                claim["id"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["claims"][0]["claim"]["id"] == claim["id"]


def test_claim_role_requires_a_known_study(tmp_path):
    repo = _repository(tmp_path)
    source = _claim(tmp_path, "Bad role", "headline")
    with pytest.raises(RepositoryError, match="Claim role must be one of"):
        repo.create_claim(source)


def test_registry_merge_rejects_duplicate_claim_ids(tmp_path):
    repo = _repository(tmp_path)
    repo.create_claim(_claim(tmp_path, "Main result", "main_result"))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    snapshot = compile_registry(repo)
    first.write_text(json.dumps(snapshot))
    second.write_text(json.dumps(snapshot))

    with pytest.raises(RepositoryError, match="Duplicate study ID"):
        merge_registry_snapshots([first, second])


def test_legacy_claims_remain_valid_without_study(tmp_path):
    repo = _repository(tmp_path)
    source = _write(
        tmp_path / "legacy.yaml",
        """title: Legacy claim
statement: Existing repositories remain readable.
topic: QT
model: ribbon-v1
scope: general
""",
    )
    claim = repo.create_claim(source)
    state = compile_claim_state(repo, claim["id"])

    assert state["study"] is None
    assert all(value is None for value in state["narrative"].values())
