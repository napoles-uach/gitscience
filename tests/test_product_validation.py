"""Tests for the case-study product-validation rubric."""

from validation.validate_case_studies import evaluate_fmm, evaluate_twisted


def _state(prefix: str, verifier: str, assertion: str, detail: dict):
    assumption_id = f"GS-{prefix}-0002" if prefix == "QT" else "GS-QF-0006"
    nodes = [
        {
            "id": assumption_id,
            "kind": "assumption",
            "status": "declared",
        }
    ]
    if prefix == "QT":
        nodes.append(
            {"id": "GS-QT-0003", "kind": "lemma", "status": "conditional_proven"}
        )
    artifact = {
        "runs": {
            "plus_tau": {"transmission": 3.8},
            "minus_tau": {"transmission": 3.8},
        }
    }
    if prefix == "QF":
        artifact = {
            "per_call_bad_probability_budget": 6.25e-8,
            "regimes": {
                "constant_mean": {},
                "proportional_mean": {},
                "inconsistent_hybrid": {},
            },
        }
    return {
        "claim": {"id": f"GS-{prefix}-0005"},
        "status": {
            "derived": "conditional_corroborated",
            "dimensions": {
                "computational": "corroborated",
                "provenance": "unauthenticated",
                "revision": "committed",
            },
        },
        "scope_boundary": {
            "scope": "numerical_instance",
            "limitations": [
                "The result is a finite binomial union-bound calculation.",
                "It does not establish an asymptotic theorem or a fermionic occupancy law.",
            ],
        },
        "dependency_closure": {"nodes": nodes},
        "obligations": [
            {"message": f"{assumption_id} is an explicit assumption"}
        ],
        "evidence": [
            {
                "verifier": {"name": verifier},
                "assertions": [
                    {
                        "assertion": assertion,
                        "outcome": "satisfied",
                        "detail": detail,
                    }
                ],
                "artifact_result": artifact,
            }
        ],
    }


def test_twisted_rubric_requires_conditional_interpretation():
    state = _state("QT", "kwant_transport", "transmission_even_in_tau", {})

    report = evaluate_twisted(state)

    assert all(item["passed"] for item in report["checks"])
    assert report["observations"]["transmission_is_numerically_nontrivial"] is True
    assert report["observations"]["nontriviality_was_a_declared_assertion"] is False


def test_fmm_rubric_preserves_negative_assertion_semantics():
    state = _state(
        "QF",
        "fmm_occupancy",
        "hybrid_regime_exceeds_tail_budget",
        {"observed": 1.0, "required_maximum": 6.25e-8},
    )

    report = evaluate_fmm(state)

    assert all(item["passed"] for item in report["checks"])
