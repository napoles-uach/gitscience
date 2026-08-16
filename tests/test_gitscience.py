"""Tests for the local GitScience MVP."""

import json
from pathlib import Path

import pytest

from gitscience.cli import main
from gitscience.repository import (
    GitScienceRepository,
    RepositoryError,
)
from gitscience.verification import VerificationError, verify_claim
from gitscience.verifiers import get_verifier
from gitscience_kwant.plugin import KwantTransportVerifier


def _write_yaml(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def _repository(tmp_path) -> GitScienceRepository:
    repo = GitScienceRepository.init(tmp_path / "science", "test-science")
    repo.git(["config", "user.email", "science@example.test"])
    repo.git(["config", "user.name", "Science Test"])
    repo.create_topic("Quantum transport", "QT")
    model_source = _write_yaml(
        tmp_path / "model.yaml",
        "name: Test helicoidal model\nkind: tight_binding\n",
    )
    repo.create_model("helicoidal-v1", model_source)
    return repo


def _claim_source(
    tmp_path,
    assertion="transmission_even_in_tau",
    verifier="kwant_transport",
    scope="numerical_instance",
):
    return _write_yaml(
        tmp_path / f"claim-{assertion}.yaml",
        f"""title: Test claim
statement: A testable transport statement.
topic: QT
model: helicoidal-v1
scope: {scope}
verification:
  verifier: {verifier}
  request:
    width: 4
    length: 8
    energy: 1.0
    tau: 0.1
  assertions:
    - {assertion}
    - numerical_diagnostics
""",
    )


def _fake_result(passes=True):
    return {
        "schema_version": "kwant-transport-v1",
        "claims": {
            "transmission_even_in_tau": {"passes": passes, "absolute": 1e-12},
            "polarization_x_odd_in_tau": {"passes": passes, "absolute": 1e-12},
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


def _sweep_claim_source(tmp_path):
    return _write_yaml(
        tmp_path / "claim-sweep.yaml",
        """title: Small-twist polarization scaling
statement: The odd polarization is approximately linear in small twist.
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
    linearity_tolerance: 0.06
    quadratic_tolerance: 0.05
  assertions:
    - polarization_linear_in_small_twist
    - numerical_diagnostics
""",
    )


def _commit_proposal(repo):
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", "Propose claim"])


def _mock_result(monkeypatch, result):
    monkeypatch.setattr(
        KwantTransportVerifier,
        "run",
        lambda self, experiment, request: result,
    )


def _commit_evidence(repo, evidence):
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Record evidence", "--", *paths])


def test_repository_creates_topic_model_and_claim(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))

    assert claim["id"] == "GS-QT-0001"
    assert repo.load_claim(claim["id"])["model"] == "helicoidal-v1"
    assert repo.claim_status(claim["id"]) == "proposed"
    assert (repo.root / ".git").is_dir()


def test_repository_can_share_parent_git_without_committing_siblings(tmp_path):
    root = tmp_path / "registry"
    root.mkdir()
    GitScienceRepository._run_git_at(root, ["init"])
    GitScienceRepository._run_git_at(root, ["config", "user.email", "science@example.test"])
    GitScienceRepository._run_git_at(root, ["config", "user.name", "Science Test"])
    sibling = root / "unrelated.txt"
    sibling.write_text("leave me uncommitted\n")

    repo = GitScienceRepository.init(root / "studies" / "ribbon", "Ribbon")
    repo.create_topic("Quantum transport", "QT")

    assert not (repo.root / ".git").exists()
    assert repo.git_root == root
    assert main(["-C", str(repo.root), "commit", "-m", "Initialize ribbon"]) == 0
    assert repo.committed_revision(repo.root / "topics" / "QT.yaml")
    sibling_status = repo.git(["status", "--short", "--", str(sibling)])
    assert sibling_status.startswith("?? ")
    assert sibling_status.endswith("unrelated.txt")


def test_kwant_verifier_is_discovered_as_a_plugin():
    verifier = get_verifier("kwant_transport")

    assert verifier.name == "kwant_transport"
    assert verifier.version == "0.1.0"
    assert verifier.__class__.__module__ == "gitscience_kwant.plugin"


def test_claim_rejects_uninstalled_verifier(tmp_path):
    repo = _repository(tmp_path)
    with pytest.raises(RepositoryError, match="not installed"):
        repo.create_claim(_claim_source(tmp_path, verifier="execute_python"))


def test_claim_rejects_unknown_assertion(tmp_path):
    repo = _repository(tmp_path)
    with pytest.raises(RepositoryError, match="Unsupported assertions"):
        repo.create_claim(_claim_source(tmp_path, assertion="arbitrary_code_result"))


def test_claim_accepts_trusted_small_twist_experiment(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_sweep_claim_source(tmp_path))

    assert claim["verification"]["experiment"] == "small_twist_scaling"


def test_claim_rejects_assertion_from_wrong_experiment(tmp_path):
    repo = _repository(tmp_path)
    source = _sweep_claim_source(tmp_path)
    source.write_text(
        source.read_text().replace(
            "polarization_linear_in_small_twist", "transmission_even_in_tau"
        )
    )
    with pytest.raises(RepositoryError, match="Unsupported assertions"):
        repo.create_claim(source)


def test_verification_requires_committed_claim_and_model(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))

    with pytest.raises(VerificationError, match="not committed"):
        verify_claim(repo, claim["id"])


def test_verification_writes_hashed_evidence_and_artifact(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)

    _mock_result(monkeypatch, _fake_result())
    evidence = verify_claim(repo, claim["id"])

    assert evidence["classification"] == "corroborating"
    assert evidence["claim"]["git_commit"]
    assert evidence["claim"]["sha256"] == repo.sha256(repo.claim_path(claim["id"]))
    artifact = repo.root / evidence["artifact"]["path"]
    assert evidence["artifact"]["sha256"] == repo.sha256(artifact)
    assert evidence["environment_sha256"]
    assert evidence["verification"]["verifier"] == "kwant_transport"
    assert evidence["environment"]["verifier"]["version"] == "0.1.0"
    assert evidence["authentication"] == {
        "method": "none",
        "authenticated": False,
    }
    assert evidence["verification"]["arbitrary_code_execution"] is False
    assert repo.claim_status(claim["id"]) == "proposed"
    _commit_evidence(repo, evidence)
    assert repo.claim_status(claim["id"]) == "corroborated"


def test_contradictory_evidence_contests_current_revision(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)

    _mock_result(monkeypatch, _fake_result(passes=False))
    evidence = verify_claim(repo, claim["id"])

    assert evidence["classification"] == "contradictory"
    _commit_evidence(repo, evidence)
    assert repo.claim_status(claim["id"]) == "contested"


def test_numerical_evidence_only_supports_general_claim(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path, scope="general"))
    _commit_proposal(repo)

    _mock_result(monkeypatch, _fake_result())
    evidence = verify_claim(repo, claim["id"])
    _commit_evidence(repo, evidence)

    assert repo.claim_status(claim["id"]) == "supported"


def test_changed_claim_must_be_committed_again(tmp_path):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)
    path = repo.claim_path(claim["id"])
    path.write_text(path.read_text() + "notes: changed\n")

    with pytest.raises(VerificationError, match="uncommitted changes"):
        verify_claim(repo, claim["id"])


def test_solver_failure_is_reported_as_verification_error(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)

    def failing_runner(self, experiment, request):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr(KwantTransportVerifier, "run", failing_runner)
    with pytest.raises(VerificationError, match="solver unavailable"):
        verify_claim(repo, claim["id"])


def test_cli_local_workflow(tmp_path, capsys):
    root = tmp_path / "cli-science"
    assert main(["init", str(root), "--name", "CLI test"]) == 0
    assert (
        main(
            [
                "-C",
                str(root),
                "topic",
                "create",
                "Quantum transport",
                "--code",
                "QT",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Created topic QT" in output


def test_cli_lists_claims_and_evidence(tmp_path, capsys, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)
    _mock_result(monkeypatch, _fake_result())
    evidence = verify_claim(repo, claim["id"])
    _commit_evidence(repo, evidence)

    assert main(["-C", str(repo.root), "claim", "list"]) == 0
    assert f"{claim['id']}\tcorroborated" in capsys.readouterr().out
    assert (
        main(
            [
                "-C",
                str(repo.root),
                "evidence",
                "list",
                "--claim",
                claim["id"],
            ]
        )
        == 0
    )
    assert f"{evidence['id']}\t{claim['id']}\tcorroborating" in capsys.readouterr().out


def test_cli_concise_verify_runs_claim(tmp_path, capsys, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)

    _mock_result(monkeypatch, _fake_result())

    assert main(["-C", str(repo.root), "verify", claim["id"]]) == 0
    assert f"{claim['id']}: corroborating (EV-000001" in capsys.readouterr().out
    assert repo.git(["log", "-1", "--format=%s"]) == (
        f"Record verification evidence for {claim['id']}"
    )
    assert repo.git(["status", "--short"]) == ""
    assert repo.claim_status(claim["id"]) == "corroborated"


def test_cli_explicit_verify_run_remains_supported(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)

    _mock_result(monkeypatch, _fake_result())

    assert main(["-C", str(repo.root), "verify", "run", claim["id"]]) == 0
    assert repo.git(["log", "-1", "--format=%s"]) == "Propose claim"
    assert repo.claim_status(claim["id"]) == "proposed"


def test_evidence_json_is_valid(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    claim = repo.create_claim(_claim_source(tmp_path))
    _commit_proposal(repo)
    _mock_result(monkeypatch, _fake_result())
    evidence = verify_claim(repo, claim["id"])

    stored = json.loads(repo.evidence_path(evidence["id"]).read_text())
    assert stored == evidence
