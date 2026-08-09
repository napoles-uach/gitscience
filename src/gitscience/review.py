"""Advisory review orchestration and provenance records."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from typing import Any

from .integrity import digest_json
from .repository import GitScienceRepository, RepositoryError
from .reviewers import ReviewerError, ReviewerPlugin, get_reviewer


class ReviewError(RuntimeError):
    """Raised when an advisory review cannot be run safely."""


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _environment(reviewer: ReviewerPlugin) -> dict[str, Any]:
    packages = ("gitscience", *reviewer.environment_packages)
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {name: _package_version(name) for name in dict.fromkeys(packages)},
        "reviewer": {"name": reviewer.name, "version": reviewer.version},
        "reviewer_source_sha256": {
            path.name: GitScienceRepository.sha256(path)
            for path in reviewer.source_paths()
        },
    }


def _reference(repo: GitScienceRepository, path, record_id: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "git_commit": repo.committed_revision(path),
        "sha256": repo.sha256(path),
        "path": path.relative_to(repo.root).as_posix(),
    }


def inspect_review(
    repo: GitScienceRepository, claim_id: str, reviewer_name: str
) -> dict[str, Any]:
    claim = repo.load_claim(claim_id)
    reviewer = get_reviewer(reviewer_name)
    evidence = repo.evidence_for_claim(claim_id)
    current_digest = repo.sha256(repo.claim_path(claim_id))
    current_evidence = [
        item for item in evidence if item.get("claim", {}).get("sha256") == current_digest
    ]
    return {
        "claim_id": claim_id,
        "title": claim["title"],
        "reviewer": reviewer.name,
        "reviewer_version": reviewer.version,
        "eligible_evidence": [item["id"] for item in current_evidence],
        "advisory_only": True,
        "affects_claim_status": False,
        "network_or_model_access_may_be_required": True,
    }


def review_claim(
    repo: GitScienceRepository,
    claim_id: str,
    reviewer_name: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a reviewer against committed evidence and record an advisory report."""
    claim = repo.load_claim(claim_id)
    model = repo.load_model(claim["model"])
    claim_path = repo.claim_path(claim_id)
    model_path = repo.model_path(claim["model"])
    try:
        claim_ref = _reference(repo, claim_path, claim_id)
        model_ref = _reference(repo, model_path, claim["model"])
    except RepositoryError as exc:
        raise ReviewError(str(exc)) from exc

    current_digest = claim_ref["sha256"]
    evidence_records = [
        item
        for item in repo.evidence_for_claim(claim_id)
        if item.get("claim", {}).get("sha256") == current_digest
    ]
    if not evidence_records:
        raise ReviewError("No integrity-valid committed evidence for this claim revision")

    evidence_refs = []
    dossier_evidence = []
    for evidence in evidence_records:
        evidence_path = repo.evidence_path(evidence["id"])
        evidence_refs.append(_reference(repo, evidence_path, evidence["id"]))
        artifact_path = repo.root / evidence["artifact"]["path"]
        dossier_evidence.append(
            {
                "record": evidence,
                "artifact": json.loads(artifact_path.read_text()),
            }
        )

    try:
        reviewer = get_reviewer(reviewer_name)
        result = reviewer.run(
            {"claim": claim, "model": model, "evidence": dossier_evidence},
            options or {},
        )
    except ReviewerError as exc:
        raise ReviewError(str(exc)) from exc
    except Exception as exc:
        raise ReviewError(f"Reviewer {reviewer_name} failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ReviewError("Reviewer returned a non-object result")
    verdict = str(result.get("verdict", "")).upper()
    if verdict not in {"VERIFIED", "REFUTED", "INCONCLUSIVE"}:
        raise ReviewError("Reviewer returned an unsupported verdict")

    review_id = repo.next_review_id()
    artifact_path = repo.root / "review-artifacts" / f"{review_id}.json"
    artifact_path.parent.mkdir(exist_ok=True)
    artifact_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    environment = _environment(reviewer)
    review = {
        "schema_version": "gitscience-review-v1",
        "id": review_id,
        "created_at": datetime.now(UTC).isoformat(),
        "kind": "automated_scientific_review",
        "verdict": verdict,
        "summary": str(result.get("summary", "")),
        "advisory": True,
        "affects_claim_status": False,
        "claim": claim_ref,
        "model": model_ref,
        "evidence": evidence_refs,
        "reviewer": {"name": reviewer.name, "version": reviewer.version},
        "artifact": {
            "path": artifact_path.relative_to(repo.root).as_posix(),
            "sha256": repo.sha256(artifact_path),
        },
        "environment": environment,
        "environment_sha256": digest_json(environment),
        "authentication": {"method": "none", "authenticated": False},
    }
    review_path = repo.review_path(review_id)
    review_path.parent.mkdir(exist_ok=True)
    review_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    return review
