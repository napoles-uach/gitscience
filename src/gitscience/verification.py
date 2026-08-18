"""Trusted verification and provenance records for GitScience claims."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from typing import Any

from .integrity import classification_from_evaluations, digest_json
from .repository import GitScienceRepository, RepositoryError
from .verifiers import VerifierError, VerifierPlugin, get_verifier


class VerificationError(RuntimeError):
    """Raised when a claim cannot be verified safely."""


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment_manifest(verifier: VerifierPlugin) -> dict[str, Any]:
    adapter_hashes = {
        path.name: GitScienceRepository.sha256(path) for path in verifier.source_paths()
    }
    packages = ("gitscience", *verifier.environment_packages)
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {name: _package_version(name) for name in dict.fromkeys(packages)},
        "verifier": {"name": verifier.name, "version": verifier.version},
        "verifier_source_sha256": adapter_hashes,
    }


def inspect_claim(repo: GitScienceRepository, claim_id: str) -> dict[str, Any]:
    claim = repo.load_claim(claim_id)
    if "verification" not in claim:
        raise VerificationError(f"Claim {claim_id} has no computational verifier")
    verification = claim["verification"]
    repo._validate_verification(verification)
    verifier_name = verification.get("verifier", verification.get("backend"))
    verifier = get_verifier(verifier_name)
    claim_path = repo.claim_path(claim_id)
    model_path = repo.model_path(claim["model"])
    try:
        claim_commit = repo.committed_revision(claim_path)
        claim_clean = True
    except RepositoryError as exc:
        claim_commit = str(exc)
        claim_clean = False
    try:
        model_commit = repo.committed_revision(model_path)
        model_clean = True
    except RepositoryError as exc:
        model_commit = str(exc)
        model_clean = False
    return {
        "claim_id": claim_id,
        "title": claim["title"],
        "scope": claim["scope"],
        "verifier": verifier.name,
        "verifier_version": verifier.version,
        "experiment": verification.get("experiment", verifier.default_experiment),
        "request": verification["request"],
        "assertions": verification["assertions"],
        "dependencies": claim.get("dependency_revisions", []),
        "dependency_report": repo.dependency_report(claim_id),
        "claim_committed_and_clean": claim_clean,
        "claim_revision": claim_commit,
        "model_committed_and_clean": model_clean,
        "model_revision": model_commit,
        "arbitrary_code_execution": False,
    }


def _evaluate(result: dict[str, Any], assertions: list[str]) -> list[dict[str, Any]]:
    evaluations = []
    for assertion in assertions:
        if assertion == "numerical_diagnostics":
            checks = [
                value
                for run_checks in result.get("diagnostics", {}).values()
                for value in run_checks.values()
            ]
            passed = all(checks) if checks else None
            detail = result.get("diagnostics", {})
        else:
            detail = result.get("claims", {}).get(assertion)
            passed = detail.get("passes") if isinstance(detail, dict) else None
        evaluations.append({"assertion": assertion, "passes": passed, "detail": detail})
    return evaluations


def verify_claim(repo: GitScienceRepository, claim_id: str) -> dict[str, Any]:
    claim = repo.load_claim(claim_id)
    if "verification" not in claim:
        raise VerificationError(f"Claim {claim_id} has no computational verifier")
    return verify_with_contract(repo, claim_id, claim["verification"])


def verify_with_contract(
    repo: GitScienceRepository,
    claim_id: str,
    verification: dict[str, Any],
    *,
    formalization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a claim or approved-formalization verification contract."""
    claim = repo.load_claim(claim_id)
    try:
        repo.require_locked_dependencies(claim_id)
    except RepositoryError as exc:
        raise VerificationError(str(exc)) from exc
    repo._validate_verification(verification)
    verifier_name = verification.get("verifier", verification.get("backend"))
    try:
        verifier = get_verifier(verifier_name)
    except VerifierError as exc:
        raise VerificationError(str(exc)) from exc
    claim_path = repo.claim_path(claim_id)
    model_path = repo.model_path(claim["model"])
    try:
        claim_commit = repo.committed_revision(claim_path)
        model_commit = repo.committed_revision(model_path)
    except RepositoryError as exc:
        raise VerificationError(str(exc)) from exc

    experiment = verification.get("experiment", verifier.default_experiment)
    try:
        result = verifier.run(experiment, verification["request"])
    except Exception as exc:
        raise VerificationError(f"Verifier {verifier.name} failed: {exc}") from exc
    evaluations = _evaluate(result, verification["assertions"])
    success_classification = (
        "proving" if verifier.evidence_kind == "formal_proof" else "corroborating"
    )
    classification = classification_from_evaluations(
        evaluations, success=success_classification
    )
    evidence_id = repo.next_evidence_id()
    artifact_path = repo.root / "artifacts" / f"{evidence_id}{verifier.artifact_suffix}"
    artifact_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    environment = environment_manifest(verifier)
    evidence = {
        "schema_version": "gitscience-evidence-v1",
        "id": evidence_id,
        "created_at": datetime.now(UTC).isoformat(),
        "classification": classification,
        "repository_head": repo.git(["rev-parse", "HEAD"]),
        "attestor": {
            "name": repo.git_config("user.name"),
            "email": repo.git_config("user.email"),
        },
        "claim": {
            "id": claim_id,
            "git_commit": claim_commit,
            "sha256": repo.sha256(claim_path),
            "path": claim_path.relative_to(repo.root).as_posix(),
        },
        "model": {
            "id": claim["model"],
            "git_commit": model_commit,
            "sha256": repo.sha256(model_path),
            "path": model_path.relative_to(repo.root).as_posix(),
        },
        "dependencies": claim.get("dependency_revisions", []),
        "verification": {
            "verifier": verifier.name,
            "verifier_version": verifier.version,
            "evidence_kind": verifier.evidence_kind,
            "experiment": experiment,
            "request": verification["request"],
            "assertions": verification["assertions"],
            "evaluations": evaluations,
            "arbitrary_code_execution": False,
        },
        "artifact": {
            "path": artifact_path.relative_to(repo.root).as_posix(),
            "sha256": repo.sha256(artifact_path),
        },
        "environment": environment,
        "environment_sha256": digest_json(environment),
        "authentication": {
            "method": "none",
            "authenticated": False,
        },
    }
    if formalization is not None:
        evidence["formalization"] = formalization
    evidence_path = repo.evidence_path(evidence_id)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence
