"""Versioned, human-approved requests for trusted formal verification."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .formalizers import FormalizerError, get_formalizer
from .integrity import digest_json
from .repository import GitScienceRepository, RepositoryError
from .verifiers import VerifierError, get_verifier

SCHEMA_VERSION = "gitscience-formalization-v1"
GROUNDING_STATUSES = frozenset({"unlinked", "partial", "established"})
MAPPING_STATUSES = frozenset({"exact", "partial", "open"})


class FormalizationError(RuntimeError):
    """Raised when a formalization workflow would violate its trust boundary."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _reference(
    repo: GitScienceRepository, path: Path, record_id: str
) -> dict[str, Any]:
    return {
        "id": record_id,
        "git_commit": repo.committed_revision(path),
        "sha256": repo.sha256(path),
        "path": path.relative_to(repo.root).as_posix(),
    }


def _non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FormalizationError(f"{label} must be a non-empty string")
    return value


def _validate_proposal(
    repo: GitScienceRepository, proposal: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise FormalizationError("Formalization proposal must be an object")
    allowed = {
        "summary",
        "formal_statement",
        "semantic_mapping",
        "assumptions",
        "unformalized",
        "scientific_grounding",
        "verification",
    }
    unknown = sorted(set(proposal) - allowed)
    if unknown:
        raise FormalizationError(
            f"Formalization proposal has unsupported fields: {', '.join(unknown)}"
        )
    missing = sorted(allowed - {"verification"} - set(proposal))
    if missing:
        raise FormalizationError(
            f"Formalization proposal is missing fields: {', '.join(missing)}"
        )

    normalized = dict(proposal)
    _non_empty(normalized.get("summary"), "summary")
    statement = normalized.get("formal_statement")
    if not isinstance(statement, dict) or set(statement) != {
        "language",
        "theorem_name",
        "declaration",
    }:
        raise FormalizationError(
            "formal_statement must contain language, theorem_name and declaration"
        )
    if statement.get("language") != "lean4":
        raise FormalizationError("formal_statement.language must be lean4")
    _non_empty(statement.get("theorem_name"), "formal_statement.theorem_name")
    _non_empty(statement.get("declaration"), "formal_statement.declaration")

    mapping = normalized.get("semantic_mapping")
    if not isinstance(mapping, list) or not mapping:
        raise FormalizationError("semantic_mapping must contain at least one mapping")
    for index, item in enumerate(mapping):
        if not isinstance(item, dict) or set(item) != {"source", "target", "status"}:
            raise FormalizationError(
                f"semantic_mapping[{index}] must contain source, target and status"
            )
        _non_empty(item.get("source"), f"semantic_mapping[{index}].source")
        _non_empty(item.get("target"), f"semantic_mapping[{index}].target")
        if item.get("status") not in MAPPING_STATUSES:
            raise FormalizationError(
                f"semantic_mapping[{index}].status must be exact, partial or open"
            )

    for field in ("assumptions", "unformalized"):
        values = normalized.get(field)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise FormalizationError(f"{field} must be a list of non-empty strings")

    grounding = normalized.get("scientific_grounding")
    if not isinstance(grounding, dict) or set(grounding) != {"status", "rationale"}:
        raise FormalizationError(
            "scientific_grounding must contain status and rationale"
        )
    if grounding.get("status") not in GROUNDING_STATUSES:
        raise FormalizationError(
            "scientific_grounding.status must be unlinked, partial or established"
        )
    _non_empty(grounding.get("rationale"), "scientific_grounding.rationale")
    if grounding.get("status") == "established" and (
        normalized["unformalized"]
        or any(item["status"] != "exact" for item in mapping)
    ):
        raise FormalizationError(
            "scientific grounding cannot be established while mappings or "
            "unformalized content remain open"
        )

    verification = normalized.get("verification")
    if verification is not None:
        try:
            repo._validate_verification(verification)
        except RepositoryError as exc:
            raise FormalizationError(str(exc)) from exc
        verifier_name = verification.get("verifier", verification.get("backend"))
        try:
            verifier = get_verifier(verifier_name)
        except VerifierError as exc:
            raise FormalizationError(str(exc)) from exc
        if verifier.evidence_kind != "formal_proof":
            raise FormalizationError(
                "A formalization may request only a formal-proof verifier"
            )
        catalog = getattr(verifier, "formalization_catalog", None)
        if not callable(catalog):
            raise FormalizationError(
                "Formal verifier does not expose trusted statement contracts"
            )
        matching_contracts = [
            item for item in catalog() if item.get("verification") == verification
        ]
        if len(matching_contracts) != 1:
            raise FormalizationError(
                "verification must exactly match one trusted formalization contract"
            )
        if matching_contracts[0].get("formal_statement") != statement:
            raise FormalizationError(
                "formal_statement must exactly match the selected trusted contract"
            )
    return normalized


def formal_verification_catalog() -> list[dict[str, Any]]:
    """Return machine-readable contracts exposed by trusted formal verifiers."""
    try:
        verifier = get_verifier("lean_formal")
    except VerifierError:
        return []
    catalog = getattr(verifier, "formalization_catalog", None)
    if not callable(catalog):
        return []
    return catalog()


def create_formalization(
    repo: GitScienceRepository,
    claim_id: str,
    proposal: dict[str, Any],
    proposer: dict[str, Any],
) -> dict[str, Any]:
    """Create a draft tied to exact, committed claim and model revisions."""
    proposal = _validate_proposal(repo, proposal)
    claim = repo.load_claim(claim_id)
    claim_path = repo.claim_path(claim_id)
    model_path = repo.model_path(claim["model"])
    try:
        claim_ref = _reference(repo, claim_path, claim_id)
        model_ref = _reference(repo, model_path, claim["model"])
    except RepositoryError as exc:
        raise FormalizationError(str(exc)) from exc
    if not isinstance(proposer, dict):
        raise FormalizationError("proposer must be an object")
    proposer_kind = proposer.get("kind")
    if proposer_kind not in {"human", "llm"}:
        raise FormalizationError("proposer.kind must be human or llm")
    _non_empty(proposer.get("name"), "proposer.name")

    formalization_id = repo.next_formalization_id()
    statement = dict(proposal["formal_statement"])
    statement["sha256"] = digest_json(proposal["formal_statement"])
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": formalization_id,
        "created_at": _now(),
        "status": "draft",
        "claim": claim_ref,
        "model": model_ref,
        "proposer": proposer,
        "summary": proposal["summary"],
        "formal_statement": statement,
        "semantic_mapping": proposal["semantic_mapping"],
        "assumptions": proposal["assumptions"],
        "unformalized": proposal["unformalized"],
        "scientific_grounding": proposal["scientific_grounding"],
        "verification": proposal.get("verification"),
        "semantic_approval": {"status": "pending"},
    }
    repo.write_yaml(repo.formalization_path(formalization_id), record)
    return record


def request_formalization(
    repo: GitScienceRepository,
    claim_id: str,
    formalizer_name: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask an agent for a proposal; the result remains an unapproved draft."""
    from .state import compile_claim_state

    try:
        formalizer = get_formalizer(formalizer_name)
        dossier = {
            "claim_state": compile_claim_state(repo, claim_id),
            "available_formal_verifications": formal_verification_catalog(),
            "policy": {
                "proposal_is_not_a_proof": True,
                "human_semantic_approval_required": True,
                "select_only_listed_verification_contracts": True,
                "unmapped_scientific_content_must_remain_explicit": True,
            },
        }
        proposal = formalizer.run(dossier, options or {})
    except FormalizerError as exc:
        raise FormalizationError(str(exc)) from exc
    except Exception as exc:
        raise FormalizationError(
            f"Formalizer {formalizer_name} failed: {exc}"
        ) from exc
    model = (options or {}).get("model")
    proposer = {
        "kind": "llm",
        "name": formalizer.name,
        "version": formalizer.version,
        "source_sha256": {
            path.name: repo.sha256(path) for path in formalizer.source_paths()
        },
    }
    if model:
        proposer["model"] = str(model)
    return create_formalization(repo, claim_id, proposal, proposer)


def approve_formalization(
    repo: GitScienceRepository,
    formalization_id: str,
    approver: str | None = None,
) -> dict[str, Any]:
    """Record human acceptance of the semantic mapping and lock its statement."""
    path = repo.formalization_path(formalization_id)
    record = repo.load_formalization(formalization_id)
    if record.get("status") != "draft":
        raise FormalizationError("Only a draft formalization can be approved")
    try:
        repo.committed_revision(path)
    except RepositoryError as exc:
        raise FormalizationError(
            "Commit the draft before semantic approval: " + str(exc)
        ) from exc
    report = audit_formalization(repo, path)
    if not report["valid"]:
        raise FormalizationError(
            "Invalid draft formalization: " + "; ".join(report["errors"])
        )
    claim_id = record.get("claim", {}).get("id")
    if not isinstance(claim_id, str):
        raise FormalizationError("Formalization has no valid claim reference")
    claim_path = repo.claim_path(claim_id)
    if record["claim"].get("sha256") != repo.sha256(claim_path):
        raise FormalizationError("Claim changed after the formalization was proposed")
    model_path = repo.model_path(record["model"]["id"])
    if record["model"].get("sha256") != repo.sha256(model_path):
        raise FormalizationError("Model changed after the formalization was proposed")
    statement = dict(record.get("formal_statement", {}))
    stored_digest = statement.pop("sha256", None)
    if stored_digest != digest_json(statement):
        raise FormalizationError("Formal statement digest does not match")

    identity = approver or repo.git_config("user.name")
    email = repo.git_config("user.email")
    if not identity:
        raise FormalizationError("Human approval requires --by or git user.name")
    record["status"] = "human_approved"
    record["semantic_approval"] = {
        "status": "accepted",
        "approved_at": _now(),
        "approved_by": identity,
        "approved_email": email,
        "formal_statement_sha256": stored_digest,
    }
    repo.write_yaml(path, record)
    return record


def audit_formalization(
    repo: GitScienceRepository, path: Path
) -> dict[str, Any]:
    """Validate a committed formalization before exposing it as canonical state."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        record = yaml.safe_load(path.read_text())
        if not isinstance(record, dict):
            raise TypeError("formalization root must be an object")
    except (OSError, yaml.YAMLError, TypeError) as exc:
        return {
            "id": path.stem,
            "path": path.relative_to(repo.root).as_posix(),
            "valid": False,
            "errors": [f"invalid YAML: {exc}"],
            "warnings": [],
            "record": {},
        }
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if record.get("id") != path.stem:
        errors.append("formalization ID does not match filename")
    try:
        commit = repo.committed_revision(path)
    except RepositoryError as exc:
        commit = None
        errors.append(str(exc))

    statement = record.get("formal_statement")
    if not isinstance(statement, dict):
        errors.append("formal_statement must be an object")
        statement = {}
    statement_without_digest = dict(statement)
    stored_statement_digest = statement_without_digest.pop("sha256", None)
    if stored_statement_digest != digest_json(statement_without_digest):
        errors.append("formal statement SHA-256 does not match")

    content = {
        key: record.get(key)
        for key in (
            "summary",
            "formal_statement",
            "semantic_mapping",
            "assumptions",
            "unformalized",
            "scientific_grounding",
            "verification",
        )
    }
    if isinstance(content["formal_statement"], dict):
        content["formal_statement"] = dict(content["formal_statement"])
        content["formal_statement"].pop("sha256", None)
    if content.get("verification") is None:
        content.pop("verification")
    try:
        _validate_proposal(repo, content)
    except FormalizationError as exc:
        errors.append(str(exc))

    claim_ref = record.get("claim")
    model_ref = record.get("model")
    if not isinstance(claim_ref, dict):
        errors.append("claim reference must be an object")
        claim_ref = {}
    if not isinstance(model_ref, dict):
        errors.append("model reference must be an object")
        model_ref = {}
    repo._audit_record_reference("claim", claim_ref, errors, warnings)
    repo._audit_record_reference("model", model_ref, errors, warnings)

    status = record.get("status")
    approval = record.get("semantic_approval")
    if status not in {"draft", "human_approved"}:
        errors.append("unsupported formalization status")
    if status == "draft":
        if approval != {"status": "pending"}:
            errors.append("draft formalization must have pending approval")
    elif not isinstance(approval, dict) or (
        approval.get("status") != "accepted"
        or approval.get("formal_statement_sha256") != stored_statement_digest
        or not approval.get("approved_by")
    ):
        errors.append("human approval does not lock the formal statement")
    return {
        "id": record.get("id", path.stem),
        "path": path.relative_to(repo.root).as_posix(),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "git_commit": commit,
        "record": record,
    }


def formalizations_for_claim(
    repo: GitScienceRepository, claim_id: str, claim_digest: str | None = None
) -> list[dict[str, Any]]:
    reports = []
    for path in sorted((repo.root / "formalizations").glob("FM-*.yaml")):
        report = audit_formalization(repo, path)
        record = report["record"]
        if not report["valid"] or record.get("claim", {}).get("id") != claim_id:
            continue
        if claim_digest and record.get("claim", {}).get("sha256") != claim_digest:
            continue
        reports.append(report)
    return reports


def verify_formalization(
    repo: GitScienceRepository, formalization_id: str
) -> dict[str, Any]:
    """Run the trusted proof contract selected by an approved formalization."""
    from .verification import verify_with_contract

    path = repo.formalization_path(formalization_id)
    report = audit_formalization(repo, path)
    if not report["valid"]:
        raise FormalizationError("Invalid formalization: " + "; ".join(report["errors"]))
    record = report["record"]
    if record.get("status") != "human_approved":
        raise FormalizationError("Human semantic approval is required before Lean runs")
    verification = record.get("verification")
    if verification is None:
        raise FormalizationError(
            "No trusted Lean verification contract matches this formalization"
        )
    claim_id = record["claim"]["id"]
    if record["claim"]["sha256"] != repo.sha256(repo.claim_path(claim_id)):
        raise FormalizationError("Claim changed after semantic approval")
    formalization_ref = {
        "id": formalization_id,
        "git_commit": report["git_commit"],
        "sha256": repo.sha256(path),
        "path": path.relative_to(repo.root).as_posix(),
        "formal_statement_sha256": record["formal_statement"]["sha256"],
        "semantic_approval": "accepted",
        "scientific_grounding": record["scientific_grounding"]["status"],
    }
    return verify_with_contract(
        repo, claim_id, verification, formalization=formalization_ref
    )


def formalization_inspection(
    repo: GitScienceRepository, claim_id: str
) -> dict[str, Any]:
    claim = repo.load_claim(claim_id)
    return {
        "claim_id": claim_id,
        "title": claim["title"],
        "available_formal_verifications": formal_verification_catalog(),
        "workflow": [
            "agent_proposal",
            "human_semantic_approval",
            "trusted_lean_verification",
            "canonical_state_publication",
        ],
        "arbitrary_llm_generated_code_execution": False,
    }
