"""Export canonical GitScience records for public registries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .repository import GitScienceRepository, RepositoryError
from .state import compile_claim_state

SCHEMA_VERSION = "gitscience-observatory-v1"
MANIFEST_SCHEMA_VERSION = "gitscience-registry-manifest-v1"
ARTICLE_SCHEMA_VERSION = "gitscience-article-v1"
EQUATION_SCHEMA_VERSION = "gitscience-equation-v1"
EQUATION_ROLES = frozenset(
    {"definition", "assumption", "derived_result", "numerical_result"}
)


def _repository_revision(repo: GitScienceRepository) -> str | None:
    try:
        return repo.git(["rev-parse", "HEAD"])
    except RepositoryError:
        return None


def _all_claims(repo: GitScienceRepository) -> list[dict[str, Any]]:
    return [
        repo.load_yaml(path)
        for path in sorted((repo.root / "claims").glob("GS-*.yaml"))
    ]


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


def _study_record_path(repo: GitScienceRepository, value: Any, directory: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RepositoryError(f"Study {directory} path must be a non-empty string")
    candidate = Path(value)
    expected_root = (repo.root / directory).resolve()
    resolved = (repo.root / candidate).resolve()
    if candidate.is_absolute() or not resolved.is_relative_to(expected_root):
        raise RepositoryError(f"Study {directory} path escapes {directory}/")
    return resolved


def _source_metadata(repo: GitScienceRepository, path: Path) -> dict[str, Any]:
    try:
        commit = repo.committed_revision(path)
        state = "committed"
    except RepositoryError:
        commit = None
        state = "uncommitted"
    return {
        "path": path.relative_to(repo.root).as_posix(),
        "sha256": repo.sha256(path),
        "git_commit": commit,
        "state": state,
    }


def _load_equations(
    repo: GitScienceRepository,
    study: dict[str, Any],
) -> list[dict[str, Any]]:
    directory_value = study.get("equation_directory")
    if directory_value is None:
        return []
    directory = _study_record_path(repo, directory_value, "equations")
    if not directory.is_dir():
        raise RepositoryError(f"Missing equation directory: {directory_value}")
    equations = []
    equation_ids: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        equation = repo.load_yaml(path)
        if equation.get("schema_version") != EQUATION_SCHEMA_VERSION:
            raise RepositoryError(f"Unsupported equation schema in {path}")
        equation_id = equation.get("id")
        if not isinstance(equation_id, str) or not equation_id:
            raise RepositoryError(f"Equation without an ID in {path}")
        if equation_id in equation_ids:
            raise RepositoryError(f"Duplicate equation ID: {equation_id}")
        equation_ids.add(equation_id)
        if equation.get("study") != study["id"]:
            raise RepositoryError(f"Equation {equation_id} belongs to another study")
        if equation.get("role") not in EQUATION_ROLES:
            raise RepositoryError(f"Equation {equation_id} has an unsupported role")
        for field in ("latex", "plain_language"):
            if not isinstance(equation.get(field), str) or not equation[field].strip():
                raise RepositoryError(f"Equation {equation_id} requires {field}")
        depends_on = equation.get("depends_on", [])
        claim_ids = equation.get("claim_ids", [])
        if not isinstance(depends_on, list) or not all(
            isinstance(item, str) for item in depends_on
        ):
            raise RepositoryError(f"Equation {equation_id} has invalid depends_on")
        if not isinstance(claim_ids, list) or not all(
            isinstance(item, str) for item in claim_ids
        ):
            raise RepositoryError(f"Equation {equation_id} has invalid claim_ids")
        equation["source"] = _source_metadata(repo, path)
        equations.append(equation)
    for equation in equations:
        unknown = sorted(set(equation.get("depends_on", [])) - equation_ids)
        if unknown:
            raise RepositoryError(
                f"Equation {equation['id']} has unknown dependencies: {', '.join(unknown)}"
            )
    return equations


def _load_article(
    repo: GitScienceRepository,
    study: dict[str, Any],
    equations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any] | None:
    path_value = study.get("article_path")
    if path_value is None:
        return None
    path = _study_record_path(repo, path_value, "articles")
    if not path.is_file():
        raise RepositoryError(f"Missing study article: {path_value}")
    article = repo.load_yaml(path)
    if article.get("schema_version") != ARTICLE_SCHEMA_VERSION:
        raise RepositoryError(f"Unsupported article schema in {path}")
    if article.get("study") != study["id"]:
        raise RepositoryError(f"Article {path} belongs to another study")
    if not isinstance(article.get("title"), str) or not article["title"].strip():
        raise RepositoryError(f"Article {path} requires a title")
    sections = article.get("sections")
    if not isinstance(sections, list) or not sections:
        raise RepositoryError(f"Article {path} requires at least one section")
    equation_ids = {equation["id"] for equation in equations}
    claim_ids = {claim["id"] for claim in claims}
    section_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            raise RepositoryError(f"Article {path} contains an invalid section")
        section_id = section.get("id")
        if not isinstance(section_id, str) or not section_id:
            raise RepositoryError(f"Article {path} contains a section without an ID")
        if section_id in section_ids:
            raise RepositoryError(f"Duplicate article section ID: {section_id}")
        section_ids.add(section_id)
        if not isinstance(section.get("title"), str) or not section["title"].strip():
            raise RepositoryError(f"Article section {section_id} requires a title")
        blocks = section.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise RepositoryError(f"Article section {section_id} has no blocks")
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") not in {
                "prose",
                "equation",
                "claim",
            }:
                raise RepositoryError(f"Article section {section_id} has an invalid block")
            if block["type"] == "prose" and (
                not isinstance(block.get("text"), str) or not block["text"].strip()
            ):
                raise RepositoryError(f"Article section {section_id} has empty prose")
            if block["type"] == "equation" and block.get("ref") not in equation_ids:
                raise RepositoryError(
                    f"Article section {section_id} references an unknown equation"
                )
            if block["type"] == "claim" and block.get("ref") not in claim_ids:
                raise RepositoryError(
                    f"Article section {section_id} references an unknown claim"
                )
    article["source"] = _source_metadata(repo, path)
    return article


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
        equations = _load_equations(repo, study)
        known_claim_ids = {claim["id"] for claim in study_claims}
        for equation in equations:
            unknown_claims = sorted(set(equation.get("claim_ids", [])) - known_claim_ids)
            if unknown_claims:
                raise RepositoryError(
                    f"Equation {equation['id']} references unknown claims: "
                    + ", ".join(unknown_claims)
                )
        article = _load_article(repo, study, equations, study_claims)
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
                "article": article,
                "equations": equations,
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


def merge_registry_data(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge validated registry data into one public registry."""
    sources: list[dict[str, Any]] = []
    studies: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    study_ids: set[str] = set()
    claim_ids: set[str] = set()

    for snapshot in snapshots:
        if snapshot.get("schema_version") != SCHEMA_VERSION:
            raise RepositoryError("Unsupported registry snapshot schema")
        for study in snapshot.get("studies", []):
            if study["id"] in study_ids:
                raise RepositoryError(f"Duplicate study ID: {study['id']}")
            study_ids.add(study["id"])
            studies.append(study)
        for state in snapshot.get("claims", []):
            claim_id = state.get("claim", {}).get("id")
            if not claim_id:
                raise RepositoryError("Registry claim without an ID")
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


def merge_registry_snapshots(paths: list[Path]) -> dict[str, Any]:
    """Merge independently exported repositories into one public registry."""
    snapshots = []
    for path in paths:
        try:
            snapshot = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise RepositoryError(f"Could not read registry snapshot {path}: {exc}") from exc
        snapshots.append(snapshot)
    try:
        return merge_registry_data(snapshots)
    except RepositoryError as exc:
        raise RepositoryError(f"Invalid registry snapshot: {exc}") from exc


def compile_central_registry(manifest_path: Path) -> dict[str, Any]:
    """Build one registry from multiple GitScience studies in a shared Git repo."""
    manifest_path = manifest_path.resolve()
    try:
        manifest = yaml.safe_load(manifest_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise RepositoryError(f"Could not read registry manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise RepositoryError("Registry manifest must be a YAML object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise RepositoryError("Unsupported registry manifest schema")
    entries = manifest.get("studies")
    if not isinstance(entries, list) or not entries:
        raise RepositoryError("Registry manifest requires at least one study")
    public_url = manifest.get("public_url")
    if public_url is not None and not isinstance(public_url, str):
        raise RepositoryError("Registry public_url must be a string")

    manifest_root = manifest_path.parent
    snapshots = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RepositoryError("Each registry study requires a relative path")
        relative = Path(entry["path"])
        study_root = (manifest_root / relative).resolve()
        if relative.is_absolute() or not study_root.is_relative_to(manifest_root):
            raise RepositoryError("Registry study path escapes the manifest directory")
        repo = GitScienceRepository(study_root)
        claim_ids = entry.get("claims")
        if claim_ids is not None and (
            not isinstance(claim_ids, list)
            or not all(isinstance(claim_id, str) for claim_id in claim_ids)
        ):
            raise RepositoryError(f"Registry study {relative} has invalid claims")
        revision = _repository_revision(repo)
        source_url = None
        if public_url:
            source_url = f"{public_url.rstrip('/')}/tree/{revision or 'main'}/{relative.as_posix()}"
        snapshots.append(compile_registry(repo, claim_ids, source_url))
    registry = merge_registry_data(snapshots)
    registry["registry"] = {
        "name": manifest.get("name", "GitScience Registry"),
        "public_url": public_url,
        "manifest_path": manifest_path.name,
    }
    return registry
