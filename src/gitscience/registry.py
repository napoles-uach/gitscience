"""Export canonical GitScience records for public registries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import GitScienceRepository, RepositoryError
from .state import compile_claim_state

SCHEMA_VERSION = "gitscience-observatory-v1"


def _repository_revision(repo: GitScienceRepository) -> str | None:
    try:
        return repo.git(["rev-parse", "HEAD"])
    except RepositoryError:
        return None


def _all_claims(repo: GitScienceRepository) -> list[dict[str, Any]]:
    claims = []
    for path in sorted((repo.root / "claims").glob("GS-*.yaml")):
        claim = repo.load_yaml(path)
        claims.append(claim)
    return claims


def _claim_index_entry(
    repo: GitScienceRepository, claim: dict[str, Any], shown: set[str]
) -> dict[str, Any]:
    return {
        "id": claim["id"],
        "title": claim["title"],
        "kind": claim.get("kind", "proposition"),
        "role": claim.get("role"),
        "status": repo.claim_status(claim["id"]),
        "shown": claim["id"] in shown,
    }


def compile_registry(
    repo: GitScienceRepository,
    claim_ids: list[str] | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Compile a registry snapshot, optionally with only selected full states."""
    all_claims = _all_claims(repo)
    known = {claim["id"]: claim for claim in all_claims}
    selected_ids = sorted(known) if claim_ids is None else list(dict.fromkeys(claim_ids))
    unknown = [claim_id for claim_id in selected_ids if claim_id not in known]
    if unknown:
        raise RepositoryError(f"Unknown claims: {', '.join(unknown)}")
    shown = set(selected_ids)

    studies = []
    selected_studies = sorted(
        {
            known[claim_id].get("study")
            for claim_id in selected_ids
            if known[claim_id].get("study")
        }
    )
    for study_id in selected_studies:
        study = repo.load_study(study_id)
        study_claims = [claim for claim in all_claims if claim.get("study") == study_id]
        index = [
            _claim_index_entry(repo, claim, shown)
            for claim in sorted(study_claims, key=lambda item: item["id"])
        ]
        shown_count = sum(item["shown"] for item in index)
        main_results = [item["id"] for item in index if item["role"] == "main_result"]
        studies.append(
            {
                "id": study_id,
                "name": study["name"],
                "research_question": study["research_question"],
                "approach_summary": study["approach_summary"],
                "resolution_summary": study["resolution_summary"],
                "headline_claim_ids": main_results,
                "coverage": {
                    "shown": shown_count,
                    "total": len(index),
                    "is_complete": shown_count == len(index),
                },
                "claim_index": index,
                "record": study,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "sources": [
            {
                "repository_name": repo.name,
                "git_commit": _repository_revision(repo),
                "public_url": source_url,
            }
        ],
        "studies": studies,
        "claims": [compile_claim_state(repo, claim_id) for claim_id in selected_ids],
        "interpretation_policy": {
            "registry_is_not_a_truth_ranking": True,
            "coverage_must_be_disclosed": True,
            "claim_status_remains_conditional_on_scope_and_dependencies": True,
        },
    }


def merge_registry_snapshots(paths: list[Path]) -> dict[str, Any]:
    """Merge independently exported repositories into one public registry."""
    sources: list[dict[str, Any]] = []
    studies: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    study_ids: set[str] = set()
    claim_ids: set[str] = set()

    for path in paths:
        try:
            snapshot = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryError(f"Could not read registry snapshot {path}: {exc}") from exc
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise RepositoryError(f"Unsupported registry snapshot schema in {path}")
        for study in snapshot.get("studies", []):
            if study["id"] in study_ids:
                raise RepositoryError(f"Duplicate study ID: {study['id']}")
            study_ids.add(study["id"])
            studies.append(study)
        for state in snapshot.get("claims", []):
            claim_id = state.get("claim", {}).get("id")
            if not claim_id:
                raise RepositoryError(f"Registry claim without an ID in {path}")
            if claim_id in claim_ids:
                raise RepositoryError(f"Duplicate claim ID: {claim_id}")
            claim_ids.add(claim_id)
            claims.append(state)
        sources.extend(snapshot.get("sources", []))

    return {
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "studies": sorted(studies, key=lambda item: item["id"]),
        "claims": sorted(claims, key=lambda item: item["claim"]["id"]),
        "interpretation_policy": {
            "registry_is_not_a_truth_ranking": True,
            "coverage_must_be_disclosed": True,
            "claim_status_remains_conditional_on_scope_and_dependencies": True,
        },
    }
