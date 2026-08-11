#!/usr/bin/env python3
"""Evaluate whether canonical state exposes the intended scientific caveats."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gitscience.repository import GitScienceRepository
from gitscience.state import compile_claim_state


def _check(
    check_id: str,
    description: str,
    observed: Any,
    expected: Any,
    predicate: Callable[[Any, Any], bool] | None = None,
) -> dict[str, Any]:
    comparison = predicate or (lambda actual, target: actual == target)
    return {
        "id": check_id,
        "description": description,
        "passed": bool(comparison(observed, expected)),
        "observed": observed,
        "expected": expected,
    }


def _node(state: dict[str, Any], claim_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in state["dependency_closure"]["nodes"]
            if item["id"] == claim_id
        ),
        None,
    )


def _assertion(state: dict[str, Any], assertion_id: str) -> dict[str, Any] | None:
    return next(
        (
            assertion
            for evidence in state["evidence"]
            for assertion in evidence["assertions"]
            if assertion["assertion"] == assertion_id
        ),
        None,
    )


def _has_obligation(state: dict[str, Any], fragment: str) -> bool:
    return any(fragment in item["message"] for item in state["obligations"])


def _has_limitation(state: dict[str, Any], fragment: str) -> bool:
    return any(fragment in item for item in state["scope_boundary"]["limitations"])


def _artifact(state: dict[str, Any], verifier: str) -> dict[str, Any]:
    return next(
        item["artifact_result"]
        for item in state["evidence"]
        if item["verifier"]["name"] == verifier
    )


def evaluate_twisted(state: dict[str, Any]) -> dict[str, Any]:
    assumption = _node(state, "GS-QT-0002")
    lemma = _node(state, "GS-QT-0003")
    symmetry = _assertion(state, "transmission_even_in_tau")
    artifact = _artifact(state, "kwant_transport")
    declared_assertions = [
        item["assertion"]
        for evidence in state["evidence"]
        for item in evidence["assertions"]
    ]
    transmissions = {
        name: artifact["runs"][name]["transmission"]
        for name in ("plus_tau", "minus_tau")
    }
    checks = [
        _check(
            "twisted.status",
            "The numerical result remains conditional rather than becoming a proof.",
            state["status"]["derived"],
            "conditional_corroborated",
        ),
        _check(
            "twisted.scope",
            "The result is explicitly limited to a numerical instance.",
            state["scope_boundary"]["scope"],
            "numerical_instance",
        ),
        _check(
            "twisted.computation",
            "Kwant is represented as computational corroboration.",
            state["status"]["dimensions"]["computational"],
            "corroborated",
        ),
        _check(
            "twisted.assumption",
            "The transitive closure exposes the physical covariance assumption.",
            None if assumption is None else assumption["kind"],
            "assumption",
        ),
        _check(
            "twisted.formal_boundary",
            "The Lean-backed lemma remains conditional on its premises.",
            None if lemma is None else lemma["status"],
            "conditional_proven",
        ),
        _check(
            "twisted.open_obligation",
            "The final state repeats the hidden transitive assumption as an obligation.",
            _has_obligation(state, "GS-QT-0002 is an explicit assumption"),
            True,
        ),
        _check(
            "twisted.assertion",
            "The declared point-symmetry assertion is satisfied.",
            None if symmetry is None else symmetry["outcome"],
            "satisfied",
        ),
        _check(
            "twisted.provenance",
            "Unsigned evidence is not presented as authenticated.",
            state["status"]["dimensions"]["provenance"],
            "unauthenticated",
        ),
        _check(
            "twisted.revisions",
            "Claim and model revisions are committed.",
            state["status"]["dimensions"]["revision"],
            "committed",
        ),
    ]
    return {
        "case": "twisted_ribbon_reference_point",
        "claim_id": state["claim"]["id"],
        "checks": checks,
        "observations": {
            "transmission_values": transmissions,
            "transmission_is_numerically_nontrivial": min(transmissions.values())
            > 1e-6,
            "nontriviality_was_a_declared_assertion": "transmission_nontrivial"
            in declared_assertions,
        },
        "known_blind_spots": [
            "Nontrivial transmission is visible in the artifact but was not a declared assertion.",
            "The correspondence between the written Hamiltonian, the Kwant implementation, and the abstract Lean objects is not formally established.",
            "One parameter point does not establish symmetry across energies, geometries, or discretizations.",
        ],
    }


def evaluate_fmm(state: dict[str, Any]) -> dict[str, Any]:
    assumption = _node(state, "GS-QF-0006")
    hybrid = _assertion(state, "hybrid_regime_exceeds_tail_budget")
    artifact = _artifact(state, "fmm_occupancy")
    dependency_ids = [
        item["id"] for item in state["dependency_closure"]["nodes"]
    ]
    hybrid_detail = {} if hybrid is None else hybrid["detail"]
    checks = [
        _check(
            "fmm.status",
            "The finite calculation remains conditional corroboration.",
            state["status"]["derived"],
            "conditional_corroborated",
        ),
        _check(
            "fmm.scope",
            "The result is explicitly limited to a numerical instance.",
            state["scope_boundary"]["scope"],
            "numerical_instance",
        ),
        _check(
            "fmm.assumption",
            "The independent-uniform occupancy model remains an assumption.",
            None if assumption is None else assumption["kind"],
            "assumption",
        ),
        _check(
            "fmm.open_obligation",
            "The final state exposes the occupancy assumption as unresolved.",
            _has_obligation(state, "GS-QF-0006 is an explicit assumption"),
            True,
        ),
        _check(
            "fmm.hybrid_rejected",
            "The positive assertion means that the inconsistent hybrid exceeds its budget.",
            None if hybrid is None else hybrid["outcome"],
            "satisfied",
        ),
        _check(
            "fmm.hybrid_probability",
            "The hybrid bad-probability bound is above the allowed maximum.",
            hybrid_detail.get("observed"),
            hybrid_detail.get("required_maximum"),
            lambda observed, maximum: observed is not None
            and maximum is not None
            and observed > maximum,
        ),
        _check(
            "fmm.finite_limit",
            "The state says that the result is a finite binomial calculation.",
            _has_limitation(state, "finite binomial"),
            True,
        ),
        _check(
            "fmm.no_asymptotic_overclaim",
            "The state explicitly denies an asymptotic or fermionic conclusion.",
            _has_limitation(state, "does not establish an asymptotic theorem"),
            True,
        ),
        _check(
            "fmm.graph_separation",
            "The finite diagnostic does not falsely depend on the general FMM corollary.",
            "GS-QF-0005" in dependency_ids,
            False,
        ),
        _check(
            "fmm.provenance",
            "Unsigned evidence is not presented as authenticated.",
            state["status"]["dimensions"]["provenance"],
            "unauthenticated",
        ),
    ]
    return {
        "case": "quantum_fmm_occupancy_regimes",
        "claim_id": state["claim"]["id"],
        "checks": checks,
        "observations": {
            "per_call_bad_probability_budget": artifact[
                "per_call_bad_probability_budget"
            ],
            "constant_mean": artifact["regimes"]["constant_mean"],
            "proportional_mean": artifact["regimes"]["proportional_mean"],
            "inconsistent_hybrid": artifact["regimes"]["inconsistent_hybrid"],
        },
        "known_blind_spots": [
            "The independent occupancy model is not a model of generic fermionic states.",
            "The finite diagnostic does not control occupancy throughout kinetic evolution.",
            "The analytic restricted-circuit error bound remains an assumption.",
        ],
    }


def _load_state(repo_path: Path, claim_id: str) -> tuple[dict[str, Any], bool]:
    repo = GitScienceRepository(repo_path)
    first = compile_claim_state(repo, claim_id)
    second = compile_claim_state(repo, claim_id)
    return first, first == second


def run_validation(twisted_repo: Path, fmm_repo: Path) -> dict[str, Any]:
    twisted_state, twisted_deterministic = _load_state(
        twisted_repo, "GS-QT-0005"
    )
    fmm_state, fmm_deterministic = _load_state(fmm_repo, "GS-QF-0007")
    cases = [evaluate_twisted(twisted_state), evaluate_fmm(fmm_state)]
    cases[0]["checks"].append(
        _check(
            "twisted.deterministic",
            "Repeated compilation produces the same canonical object.",
            twisted_deterministic,
            True,
        )
    )
    cases[1]["checks"].append(
        _check(
            "fmm.deterministic",
            "Repeated compilation produces the same canonical object.",
            fmm_deterministic,
            True,
        )
    )
    checks = [check for case in cases for check in case["checks"]]
    passed = sum(check["passed"] for check in checks)
    return {
        "schema_version": "gitscience-product-validation-v1",
        "summary": {
            "checks_passed": passed,
            "checks_total": len(checks),
            "structural_validation_passed": passed == len(checks),
            "external_human_replication": "pending",
            "blinded_llm_interpretation": "pending",
            "decision": (
                "continue_as_research_prototype"
                if passed == len(checks)
                else "simplify_or_repair_before_expansion"
            ),
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--twisted-repo", type=Path, required=True)
    parser.add_argument("--fmm-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_validation(args.twisted_repo, args.fmm_repo)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["summary"]["structural_validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
