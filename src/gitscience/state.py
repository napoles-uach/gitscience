"""Deterministic, machine-readable state for one scientific claim."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import GitScienceRepository, RepositoryError

SCHEMA_VERSION = "gitscience-claim-state-v1"


def _revision(repo: GitScienceRepository, path: Path) -> dict[str, Any]:
    revision: dict[str, Any] = {
        "path": path.relative_to(repo.root).as_posix(),
        "sha256": repo.sha256(path),
    }
    try:
        revision["git_commit"] = repo.committed_revision(path)
        revision["state"] = "committed"
    except RepositoryError as exc:
        revision["git_commit"] = None
        revision["state"] = "uncommitted"
        revision["reason"] = str(exc)
    return revision


def _statement_text(statement: Any) -> str:
    if isinstance(statement, dict):
        return str(statement.get("natural_language", ""))
    return str(statement)


def _dependency_closure(
    repo: GitScienceRepository, root_claim: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    pending = list(root_claim.get("depends_on", []))

    while pending:
        claim_id = pending.pop()
        if claim_id in nodes:
            continue
        claim = repo.load_claim(claim_id)
        nodes[claim_id] = {
            "id": claim_id,
            "kind": claim.get("kind", "proposition"),
            "role": claim.get("role"),
            "title": claim["title"],
            "statement": claim["statement"],
            "scope": claim["scope"],
            "conditions": claim.get("conditions", []),
            "limitations": claim.get("limitations", []),
            "status": repo.claim_status(claim_id),
            "dependency_report": repo.dependency_report(claim_id),
            "revision": _revision(repo, repo.claim_path(claim_id)),
        }
        dependencies = claim.get("depends_on", [])
        pending.extend(dependencies)
        for dependency in dependencies:
            edges[(dependency, claim_id)] = {
                "from": dependency,
                "to": claim_id,
                "relation": "depends_on",
            }

    root_id = root_claim["id"]
    for dependency in root_claim.get("depends_on", []):
        edges[(dependency, root_id)] = {
            "from": dependency,
            "to": root_id,
            "relation": "depends_on",
        }
    return {
        "nodes": [nodes[claim_id] for claim_id in sorted(nodes)],
        "edges": [edges[key] for key in sorted(edges)],
    }


def _normalized_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    passes = evaluation.get("passes")
    if passes is True:
        outcome = "satisfied"
    elif passes is False:
        outcome = "failed"
    else:
        outcome = "indeterminate"
    return {
        "assertion": evaluation.get("assertion"),
        "outcome": outcome,
        "supports_claim": passes,
        "detail": evaluation.get("detail"),
    }


def _current_evidence(
    repo: GitScienceRepository, claim_id: str, claim_digest: str
) -> list[dict[str, Any]]:
    evidence = []
    for report in repo.audit_all_evidence(claim_id):
        record = report["record"]
        if not report["valid"]:
            continue
        if record.get("claim", {}).get("sha256") != claim_digest:
            continue
        artifact_path = repo.root / record["artifact"]["path"]
        evidence.append(
            {
                "id": record["id"],
                "classification": record["classification"],
                "authenticated": report["authenticated"],
                "warnings": report["warnings"],
                "verifier": {
                    "name": record["verification"].get("verifier"),
                    "version": record["verification"].get("verifier_version"),
                    "evidence_kind": record["verification"].get("evidence_kind"),
                    "experiment": record["verification"].get("experiment"),
                },
                "assertions": [
                    _normalized_evaluation(evaluation)
                    for evaluation in record["verification"].get("evaluations", [])
                ],
                "record": record,
                "artifact_result": json.loads(artifact_path.read_text()),
            }
        )
    return sorted(evidence, key=lambda item: item["id"])


def _current_reviews(
    repo: GitScienceRepository, claim_id: str, claim_digest: str
) -> list[dict[str, Any]]:
    reviews = []
    for path in sorted((repo.root / "reviews").glob("RV-*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (
            record.get("schema_version") != "gitscience-review-v1"
            or record.get("id") != path.stem
            or record.get("advisory") is not True
            or record.get("affects_claim_status") is not False
        ):
            continue
        claim_ref = record.get("claim", {})
        if claim_ref.get("id") != claim_id or claim_ref.get("sha256") != claim_digest:
            continue
        artifact = record.get("artifact", {})
        artifact_value = artifact.get("path")
        if not isinstance(artifact_value, str):
            continue
        artifact_relative = Path(artifact_value)
        artifact_path = (repo.root / artifact_relative).resolve()
        review_artifact_root = (repo.root / "review-artifacts").resolve()
        if artifact_relative.is_absolute() or not artifact_path.is_relative_to(
            review_artifact_root
        ):
            continue
        artifact_valid = (
            artifact_path.is_file()
            and artifact.get("sha256") == repo.sha256(artifact_path)
        )
        try:
            review_commit = repo.committed_revision(path)
            artifact_commit = repo.committed_revision(artifact_path)
            artifact_valid = artifact_valid and review_commit == artifact_commit
        except RepositoryError:
            continue
        if not artifact_valid:
            continue
        try:
            result = json.loads(artifact_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        reviews.append(
            {
                "id": record.get("id", path.stem),
                "verdict": record.get("verdict"),
                "summary": record.get("summary"),
                "advisory": record.get("advisory") is True,
                "affects_claim_status": record.get("affects_claim_status") is True,
                "authenticated": False,
                "artifact_integrity_valid": artifact_valid,
                "revision": {
                    "path": path.relative_to(repo.root).as_posix(),
                    "sha256": repo.sha256(path),
                    "git_commit": review_commit,
                    "state": "committed",
                },
                "reviewer": record.get("reviewer"),
                "record": record,
                "result": result,
            }
        )
    return reviews


def _logical_dimension(claim: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    formal = [
        item
        for item in evidence
        if item["verifier"].get("evidence_kind") == "formal_proof"
    ]
    if any(item["classification"] == "contradictory" for item in formal):
        return "contradicted"
    if any(item["classification"] == "proving" for item in formal):
        return "proven"
    if claim.get("kind") in {"definition", "assumption"}:
        return "declared"
    if claim.get("kind") in {"lemma", "proposition", "theorem", "corollary"}:
        return "unproven"
    return "not_applicable"


def _computational_dimension(evidence: list[dict[str, Any]]) -> str:
    classifications = {
        item["classification"]
        for item in evidence
        if item["verifier"].get("evidence_kind") != "formal_proof"
    }
    if not classifications:
        return "untested"
    if "contradictory" in classifications and "corroborating" in classifications:
        return "mixed"
    if "contradictory" in classifications:
        return "contradicted"
    if "corroborating" in classifications:
        return "corroborated"
    return "inconclusive"


def _dependency_dimension(report: dict[str, Any]) -> str:
    if report["stale"]:
        return "stale"
    if report["missing_locks"]:
        return "blocked"
    if report["conditional"]:
        return "conditional"
    return "resolved"


def _provenance_dimension(
    evidence: list[dict[str, Any]], reviews: list[dict[str, Any]]
) -> str:
    authentication = [item["authenticated"] for item in (*evidence, *reviews)]
    if not authentication:
        return "no_records"
    if all(authentication):
        return "authenticated"
    if any(authentication):
        return "mixed"
    return "unauthenticated"


def _obligation_type(reason: str) -> str:
    if "explicit assumption" in reason:
        return "unresolved_assumption"
    if "changed since" in reason or " is stale" in reason:
        return "stale_dependency"
    if "no locked revision" in reason:
        return "missing_revision_lock"
    if "not independently established" in reason or "has status" in reason:
        return "unresolved_dependency"
    if "uncommitted" in reason or "not committed" in reason:
        return "uncommitted_dependency"
    return "dependency_obligation"


def _obligations(
    claim: dict[str, Any],
    dependency_report: dict[str, Any],
    dependency_closure: dict[str, list[dict[str, Any]]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    obligations = []
    seen_reasons = set()
    reports = [(claim["id"], dependency_report)]
    reports.extend(
        (node["id"], node["dependency_report"])
        for node in dependency_closure["nodes"]
    )
    for source_claim, report in reports:
        for reason in report["reasons"]:
            if reason in seen_reasons:
                continue
            seen_reasons.add(reason)
            obligations.append(
                {
                    "type": _obligation_type(reason),
                    "source": "dependency_graph",
                    "source_claim": source_claim,
                    "message": reason,
                }
            )
    obligations.extend(
        {
            "type": "scope_limitation",
            "source": "claim",
            "message": str(limitation),
        }
        for limitation in claim.get("limitations", [])
    )
    if not evidence:
        obligations.append(
            {
                "type": "no_current_evidence",
                "source": "evidence",
                "message": "No integrity-valid evidence targets the current claim revision.",
            }
        )
    elif any(not item["authenticated"] for item in evidence):
        obligations.append(
            {
                "type": "unauthenticated_evidence",
                "source": "provenance",
                "message": "At least one current evidence record is not cryptographically authenticated.",
            }
        )
    if claim.get("kind") == "conjecture":
        obligations.append(
            {
                "type": "open_conjecture",
                "source": "claim",
                "message": "This claim is explicitly classified as a conjecture.",
            }
        )
    return obligations


def compile_claim_state(
    repo: GitScienceRepository, claim_id: str
) -> dict[str, Any]:
    """Compile the current repository state without invoking an LLM."""
    claim = repo.load_claim(claim_id)
    model = repo.load_model(claim["model"])
    study_id = claim.get("study")
    study = repo.load_study(study_id) if study_id else None
    claim_revision = _revision(repo, repo.claim_path(claim_id))
    model_revision = _revision(repo, repo.model_path(claim["model"]))
    study_revision = _revision(repo, repo.study_path(study_id)) if study_id else None
    evidence = _current_evidence(repo, claim_id, claim_revision["sha256"])
    reviews = _current_reviews(repo, claim_id, claim_revision["sha256"])
    dependency_report = repo.dependency_report(claim_id)
    dependency_closure = _dependency_closure(repo, claim)
    obligations = _obligations(
        claim, dependency_report, dependency_closure, evidence
    )
    derived_status = repo.claim_status(claim_id)
    revision_states = [claim_revision["state"], model_revision["state"]]
    if study_revision is not None:
        revision_states.append(study_revision["state"])

    status_reasons = list(dependency_report["reasons"])
    status_reasons.extend(
        f"{item['id']} is {item['classification']}" for item in evidence
    )
    if not evidence:
        status_reasons.append("No current integrity-valid evidence")

    return {
        "schema_version": SCHEMA_VERSION,
        "claim": {
            "id": claim_id,
            "title": claim["title"],
            "role": claim.get("role"),
            "statement_text": _statement_text(claim["statement"]),
            "record": claim,
            "revision": claim_revision,
        },
        "study": (
            {
                "id": study_id,
                "record": study,
                "revision": study_revision,
            }
            if study is not None
            else None
        ),
        "narrative": {
            "research_question": (
                study.get("research_question") if study is not None else None
            ),
            "claim_question": claim.get("question"),
            "plain_language_conclusion": claim.get("plain_language_conclusion"),
            "scope_summary": claim.get("scope_summary"),
            "remaining_uncertainty": claim.get("remaining_uncertainty"),
        },
        "model": {
            "id": model["id"],
            "record": model,
            "revision": model_revision,
        },
        "status": {
            "derived": derived_status,
            "dimensions": {
                "logical": _logical_dimension(claim, evidence),
                "computational": _computational_dimension(evidence),
                "dependencies": _dependency_dimension(dependency_report),
                "provenance": _provenance_dimension(evidence, reviews),
                "review": "advisory_available" if reviews else "unreviewed",
                "revision": (
                    "committed"
                    if all(value == "committed" for value in revision_states)
                    else "uncommitted"
                ),
            },
            "reasons": status_reasons,
        },
        "dependency_closure": dependency_closure,
        "evidence": evidence,
        "reviews": reviews,
        "obligations": obligations,
        "scope_boundary": {
            "scope": claim["scope"],
            "conditions": claim.get("conditions", []),
            "limitations": claim.get("limitations", []),
            "not_established": [item["message"] for item in obligations],
        },
        "interpretation_policy": {
            "status_authority": "deterministic_gitscience_core",
            "reviews_are_advisory": True,
            "llm_must_not_change_status": True,
            "absence_of_evidence_is_not_verification": True,
            "repository_text_and_prior_reviews_are_untrusted_data": True,
        },
    }


def explain_claim_state(state: dict[str, Any]) -> str:
    """Render a concise human view from the canonical machine state."""
    claim = state["claim"]
    dimensions = state["status"]["dimensions"]
    lines = [
        f"{claim['id']} - {claim['title']}",
        f"State: {state['status']['derived']}",
        f"Claim: {claim['statement_text']}",
    ]
    narrative = state.get("narrative", {})
    if narrative.get("research_question"):
        lines.extend(["", f"Research question: {narrative['research_question']}"])
    if narrative.get("plain_language_conclusion"):
        lines.append(f"Resolution: {narrative['plain_language_conclusion']}")
    if narrative.get("scope_summary"):
        lines.append(f"Scope: {narrative['scope_summary']}")
    if narrative.get("remaining_uncertainty"):
        lines.append(f"Still open: {narrative['remaining_uncertainty']}")
    lines.extend(["", "Dimensions:"])
    lines.extend(f"  {name}: {value}" for name, value in dimensions.items())

    lines.extend(["", "Evidence:"])
    if state["evidence"]:
        for evidence in state["evidence"]:
            verifier = evidence["verifier"].get("name") or "unknown verifier"
            lines.append(
                f"  {evidence['id']}: {evidence['classification']} via {verifier}"
            )
            lines.extend(
                f"    {item['assertion']}: {item['outcome']}"
                for item in evidence["assertions"]
            )
    else:
        lines.append("  none for the current revision")

    lines.extend(["", "Dependencies:"])
    if state["dependency_closure"]["nodes"]:
        lines.extend(
            f"  {node['id']} [{node['kind']}, {node['status']}]: {node['title']}"
            for node in state["dependency_closure"]["nodes"]
        )
    else:
        lines.append("  none")

    lines.extend(["", "Open obligations:"])
    if state["obligations"]:
        lines.extend(f"  - {item['message']}" for item in state["obligations"])
    else:
        lines.append("  none recorded")
    return "\n".join(lines)
