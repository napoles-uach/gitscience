"""Tests for the trusted quantum-FMM occupancy-tail verifier."""

from pathlib import Path

import pytest

from gitscience.repository import GitScienceRepository
from gitscience.verification import verify_claim
from gitscience_fmm import OccupancyRegimeRequest, run_occupancy_regime_experiment
from gitscience_fmm.plugin import FmmOccupancyVerifier
from gitscience_lean.plugin import LeanFormalVerifier


def _request():
    return {
        "particles": 4096,
        "calls": 20,
        "tail_error_budget": 0.01,
        "constant_mean": 1.0,
        "load_fraction": 0.5,
        "max_capacity": 512,
    }


def test_finite_regimes_meet_distinct_tail_conditions():
    result = run_occupancy_regime_experiment(_request())

    assert result["per_call_bad_probability_budget"] == pytest.approx(6.25e-8)
    assert result["regimes"]["constant_mean"]["boxes"] == 4096
    assert result["regimes"]["constant_mean"]["capacity"] == 13
    assert result["regimes"]["proportional_mean"]["boxes"] == 93
    assert result["regimes"]["proportional_mean"]["capacity"] == 89
    assert result["regimes"]["inconsistent_hybrid"]["boxes"] == 316
    assert result["regimes"]["inconsistent_hybrid"][
        "union_bound_bad_probability"
    ] == pytest.approx(1.0)
    assert all(claim["passes"] for claim in result["claims"].values())
    assert all(all(checks.values()) for checks in result["diagnostics"].values())


def test_request_rejects_unknown_code_and_invalid_bounds():
    values = _request()
    values["code"] = "print('not allowed')"
    with pytest.raises(ValueError, match="Unknown FMM occupancy parameters"):
        OccupancyRegimeRequest.from_mapping(values)

    values = _request()
    values["load_fraction"] = 1.0
    with pytest.raises(ValueError, match="load_fraction"):
        OccupancyRegimeRequest.from_mapping(values)

    values = _request()
    values["tail_error_budget"] = 1e-20
    with pytest.raises(ValueError, match="tail_error_budget"):
        OccupancyRegimeRequest.from_mapping(values)


def test_capacity_limit_fails_closed():
    values = _request()
    values["max_capacity"] = 10

    with pytest.raises(ValueError, match="capacity exceeds max_capacity"):
        run_occupancy_regime_experiment(values)


def test_plugin_restricts_experiments_and_assertions():
    verifier = FmmOccupancyVerifier()

    with pytest.raises(ValueError, match="Unsupported FMM occupancy experiment"):
        verifier.validate("repository_script", _request(), ["numerical_diagnostics"])
    with pytest.raises(ValueError, match="Unsupported assertions"):
        verifier.validate(
            "independent_occupancy_regimes", _request(), ["universal_fmm_speedup"]
        )


def test_plugin_reports_all_trusted_source_files():
    paths = FmmOccupancyVerifier().source_paths()

    assert {path.name for path in paths} == {
        "__init__.py",
        "occupancy.py",
        "plugin.py",
        "schema.py",
    }


def test_quantum_fmm_examples_form_and_verify_staged_graph(tmp_path, monkeypatch):
    fmm_verifier = FmmOccupancyVerifier()
    lean_verifier = LeanFormalVerifier()

    def get_verifier(name):
        return {"fmm_occupancy": fmm_verifier, "lean_formal": lean_verifier}[name]

    monkeypatch.setattr("gitscience.repository.get_verifier", get_verifier)
    monkeypatch.setattr("gitscience.verification.get_verifier", get_verifier)

    example = Path(__file__).parents[1] / "examples" / "quantum-fmm"
    repo = GitScienceRepository.init(tmp_path / "science", "quantum-fmm-test")
    repo.git(["config", "user.email", "fmm@example.test"])
    repo.git(["config", "user.name", "FMM Test"])
    repo.create_topic("Quantum fast multipole methods", "QF")
    repo.create_model("quantum-fmm-occupancy-v1", example / "model.yaml")
    repo.create_study("quantum-fmm", example / "study.yaml")

    claims = []
    for source in sorted((example / "formal-graph").glob("*.yaml")):
        claims.append(repo.create_claim(source))
        repo.git(["add", "-A"])
        repo.git(["commit", "-m", f"Add {source.stem}"])

    assert [claim["id"] for claim in claims] == [
        f"GS-QF-{index:04d}" for index in range(1, 10)
    ]
    assert len(repo.claim_graph()["edges"]) == 12

    evidence = verify_claim(repo, "GS-QF-0007")
    paths = [
        ".gitscience/config.json",
        repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
        evidence["artifact"]["path"],
    ]
    repo.git(["add", "--", *paths])
    repo.git(["commit", "-m", "Check occupancy regimes", "--", *paths])

    assert evidence["classification"] == "corroborating"
    assert repo.claim_status("GS-QF-0007") == "conditional_corroborated"
