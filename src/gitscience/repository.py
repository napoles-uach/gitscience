"""Local repository and record operations for GitScience."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .integrity import classification_from_evaluations, digest_json
from .verifiers import VerifierError, get_verifier

SCHEMA_VERSION = "gitscience-repository-v1"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CLAIM_KINDS = frozenset(
    {
        "definition",
        "assumption",
        "lemma",
        "proposition",
        "theorem",
        "corollary",
        "conjecture",
        "numerical_proposition",
    }
)
CLAIM_ROLES = frozenset(
    {
        "background",
        "definition",
        "assumption",
        "supporting_result",
        "main_result",
        "limitation",
        "open_question",
    }
)
STUDY_REQUIRED_FIELDS = frozenset(
    {
        "name",
        "research_question",
        "approach_summary",
        "resolution_summary",
    }
)
CLAIM_NARRATIVE_FIELDS = (
    "question",
    "plain_language_conclusion",
    "scope_summary",
    "remaining_uncertainty",
)


class RepositoryError(RuntimeError):
    """Raised for invalid GitScience repository operations."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _validate_identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise RepositoryError(
            f"Invalid {label} {value!r}; use letters, numbers, '.', '_' or '-'."
        )
    return value


class GitScienceRepository:
    """A Git repository containing versioned scientific records."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.metadata_dir = self.root / ".gitscience"
        self.config_path = self.metadata_dir / "config.json"
        if not self.config_path.exists():
            raise RepositoryError(f"Not a GitScience repository: {self.root}")

    @classmethod
    def init(cls, path: Path, name: str) -> GitScienceRepository:
        root = path.resolve()
        metadata_dir = root / ".gitscience"
        if (metadata_dir / "config.json").exists():
            raise RepositoryError(f"GitScience repository already exists: {root}")
        root.mkdir(parents=True, exist_ok=True)
        for directory in (
            "topics",
            "models",
            "studies",
            "claims",
            "evidence",
            "artifacts",
            "reviews",
            "review-artifacts",
        ):
            target = root / directory
            target.mkdir(exist_ok=True)
            (target / ".gitkeep").write_text("")
        metadata_dir.mkdir(exist_ok=True)
        config = {
            "schema_version": SCHEMA_VERSION,
            "name": name,
            "created_at": _now(),
            "next_claim": 1,
            "next_evidence": 1,
            "next_review": 1,
        }
        (metadata_dir / "config.json").write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n"
        )
        if not (root / ".git").exists():
            cls._run_git_at(root, ["init"])
        return cls(root)

    @classmethod
    def discover(cls, start: Path | None = None) -> GitScienceRepository:
        current = (start or Path.cwd()).resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".gitscience" / "config.json").exists():
                return cls(candidate)
        raise RepositoryError("No GitScience repository found in this directory tree.")

    @staticmethod
    def _run_git_at(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RepositoryError(f"git {' '.join(args)} failed: {detail}")
        return result

    def git(self, args: list[str]) -> str:
        return self._run_git_at(self.root, args).stdout.rstrip()

    def git_config(self, key: str) -> str | None:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        value = result.stdout.strip()
        return value or None

    def _load_config(self) -> dict[str, Any]:
        return json.loads(self.config_path.read_text())

    @property
    def name(self) -> str:
        return str(self._load_config()["name"])

    def _save_config(self, config: dict[str, Any]) -> None:
        self.config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def load_yaml(path: Path) -> dict[str, Any]:
        try:
            data = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise RepositoryError(f"Could not read YAML {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RepositoryError(f"Expected a YAML object in {path}")
        return data

    @staticmethod
    def write_yaml(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
        )

    def create_topic(self, name: str, code: str) -> dict[str, Any]:
        code = _validate_identifier(code.upper(), "topic code")
        path = self.root / "topics" / f"{code}.yaml"
        if path.exists():
            raise RepositoryError(f"Topic already exists: {code}")
        topic = {
            "schema_version": "gitscience-topic-v1",
            "code": code,
            "name": name,
            "created_at": _now(),
        }
        self.write_yaml(path, topic)
        return topic

    def create_model(self, model_id: str, source: Path) -> dict[str, Any]:
        model_id = _validate_identifier(model_id, "model ID")
        path = self.model_path(model_id)
        if path.exists():
            raise RepositoryError(f"Model already exists: {model_id}")
        model = self.load_yaml(source)
        model["schema_version"] = "gitscience-model-v1"
        model["id"] = model_id
        model.setdefault("created_at", _now())
        self.write_yaml(path, model)
        return model

    def create_study(self, study_id: str, source: Path) -> dict[str, Any]:
        study_id = _validate_identifier(study_id, "study ID")
        path = self.study_path(study_id)
        if path.exists():
            raise RepositoryError(f"Study already exists: {study_id}")
        study = self.load_yaml(source)
        missing = sorted(STUDY_REQUIRED_FIELDS - set(study))
        if missing:
            raise RepositoryError(f"Study is missing fields: {', '.join(missing)}")
        for field in STUDY_REQUIRED_FIELDS:
            self._validate_non_empty_text(study[field], f"study.{field}")
        study["schema_version"] = "gitscience-study-v1"
        study["id"] = study_id
        study.setdefault("created_at", _now())
        self.write_yaml(path, study)
        return study

    def create_claim(self, source: Path) -> dict[str, Any]:
        claim = self.load_yaml(source)
        required = {"title", "statement", "topic", "model", "scope"}
        missing = sorted(required - set(claim))
        if missing:
            raise RepositoryError(f"Claim is missing fields: {', '.join(missing)}")

        topic_code = _validate_identifier(str(claim["topic"]).upper(), "topic code")
        model_id = _validate_identifier(str(claim["model"]), "model ID")
        if not (self.root / "topics" / f"{topic_code}.yaml").exists():
            raise RepositoryError(f"Unknown topic: {topic_code}")
        if not self.model_path(model_id).exists():
            raise RepositoryError(f"Unknown model: {model_id}")
        if "verification" in claim:
            self._validate_verification(claim["verification"])
        if not isinstance(claim["title"], str) or not claim["title"].strip():
            raise RepositoryError("Claim title must be a non-empty string")
        self._validate_statement(claim["statement"])
        study_id = claim.get("study")
        if study_id is not None:
            if not isinstance(study_id, str):
                raise RepositoryError("Claim study must be a study ID")
            study_id = _validate_identifier(study_id, "study ID")
            self.load_study(study_id)
            claim["study"] = study_id
        role = claim.get("role")
        if role is not None and role not in CLAIM_ROLES:
            raise RepositoryError(
                f"Claim role must be one of: {', '.join(sorted(CLAIM_ROLES))}"
            )
        if role is not None and study_id is None:
            raise RepositoryError("Claim role requires a study reference")
        for field in CLAIM_NARRATIVE_FIELDS:
            if field in claim:
                self._validate_non_empty_text(claim[field], f"claim.{field}")
        if claim["scope"] not in {"numerical_instance", "general"}:
            raise RepositoryError("Claim scope must be numerical_instance or general")
        kind = claim.get("kind", "proposition")
        if kind not in CLAIM_KINDS:
            raise RepositoryError(
                f"Claim kind must be one of: {', '.join(sorted(CLAIM_KINDS))}"
            )
        dependencies = claim.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(dependency, str) for dependency in dependencies
        ):
            raise RepositoryError("depends_on must be a list of claim IDs")
        if len(set(dependencies)) != len(dependencies):
            raise RepositoryError("depends_on contains duplicate claim IDs")
        for dependency in dependencies:
            self.load_claim(dependency)

        dependency_revisions = self._capture_dependency_revisions(
            dependencies, require_committed=False
        )

        config = self._load_config()
        claim_id = f"GS-{topic_code}-{config['next_claim']:04d}"
        config["next_claim"] += 1
        self._save_config(config)

        claim["schema_version"] = "gitscience-claim-v1"
        claim["id"] = claim_id
        claim["topic"] = topic_code
        claim["model"] = model_id
        claim["kind"] = kind
        claim["depends_on"] = dependencies
        claim["dependency_revisions"] = dependency_revisions
        claim.setdefault("conditions", [])
        claim.setdefault("created_at", _now())
        self.write_yaml(self.claim_path(claim_id), claim)
        return claim

    def _capture_dependency_revisions(
        self, dependencies: list[str], *, require_committed: bool
    ) -> list[dict[str, Any]]:
        revisions = []
        for dependency in dependencies:
            path = self.claim_path(dependency)
            try:
                commit = self.committed_revision(path)
            except RepositoryError:
                if require_committed:
                    raise
                continue
            revisions.append(
                {
                    "id": dependency,
                    "git_commit": commit,
                    "sha256": self.sha256(path),
                    "path": path.relative_to(self.root).as_posix(),
                }
            )
        return revisions

    def lock_dependencies(self, claim_id: str) -> dict[str, Any]:
        claim = self.load_claim(claim_id)
        dependencies = claim.get("depends_on", [])
        claim["dependency_revisions"] = self._capture_dependency_revisions(
            dependencies, require_committed=True
        )
        self.write_yaml(self.claim_path(claim_id), claim)
        return claim

    def dependency_report(
        self, claim_id: str, _status_cache: dict[str, str] | None = None
    ) -> dict[str, Any]:
        status_cache = _status_cache if _status_cache is not None else {}
        claim = self.load_claim(claim_id)
        dependencies = claim.get("depends_on", [])
        locks = {
            lock.get("id"): lock
            for lock in claim.get("dependency_revisions", [])
            if isinstance(lock, dict) and isinstance(lock.get("id"), str)
        }
        reasons = []
        stale = False
        conditional = False
        for dependency in dependencies:
            lock = locks.get(dependency)
            if lock is None:
                reasons.append(f"{dependency} has no locked revision")
                continue
            path = self.claim_path(dependency)
            try:
                current_commit = self.committed_revision(path)
            except RepositoryError as exc:
                stale = True
                reasons.append(str(exc))
                continue
            if (
                lock.get("sha256") != self.sha256(path)
                or lock.get("git_commit") != current_commit
            ):
                stale = True
                reasons.append(f"{dependency} changed since its locked revision")
                continue
            dependency_claim = self.load_claim(dependency)
            dependency_status = self._claim_status(dependency, status_cache)
            if dependency_claim.get("kind") == "assumption":
                conditional = True
                reasons.append(f"{dependency} is an explicit assumption")
            elif dependency_status == "stale":
                stale = True
                reasons.append(f"{dependency} is stale")
            elif dependency_status in {"blocked", "contested"}:
                conditional = True
                reasons.append(f"{dependency} has status {dependency_status}")
            elif dependency_status in {"proposed", "conditional"} or dependency_status.startswith(
                "conditional_"
            ):
                conditional = True
                reasons.append(f"{dependency} is not independently established")
        missing = sorted(set(dependencies) - set(locks))
        return {
            "claim_id": claim_id,
            "ready": not stale and not missing,
            "stale": stale,
            "conditional": conditional,
            "missing_locks": missing,
            "reasons": reasons,
        }

    def require_locked_dependencies(self, claim_id: str) -> None:
        report = self.dependency_report(claim_id)
        if not report["ready"]:
            detail = "; ".join(report["reasons"]) or "dependencies are not ready"
            raise RepositoryError(f"Claim dependencies are not locked: {detail}")

    @staticmethod
    def _validate_non_empty_text(value: Any, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise RepositoryError(f"{label} must be a non-empty string")

    @staticmethod
    def _validate_statement(statement: Any) -> None:
        if isinstance(statement, str):
            if statement.strip():
                return
            raise RepositoryError("Claim statement must be non-empty")
        if not isinstance(statement, dict):
            raise RepositoryError("Claim statement must be text or a YAML object")
        natural = statement.get("natural_language")
        latex = statement.get("latex")
        if not isinstance(natural, str) or not natural.strip():
            raise RepositoryError("statement.natural_language must be non-empty")
        if latex is not None and (not isinstance(latex, str) or not latex.strip()):
            raise RepositoryError("statement.latex must be a non-empty string")

    @staticmethod
    def _validate_verification(verification: Any) -> None:
        if not isinstance(verification, dict):
            raise RepositoryError("verification must be a YAML object")
        verifier_name = verification.get("verifier", verification.get("backend"))
        if not isinstance(verifier_name, str) or not verifier_name:
            raise RepositoryError("verification.verifier must name an installed plugin")
        if (
            "verifier" in verification
            and "backend" in verification
            and verification["verifier"] != verification["backend"]
        ):
            raise RepositoryError("verification.verifier and backend disagree")
        if not isinstance(verification.get("request"), dict):
            raise RepositoryError("verification.request must be a YAML object")
        assertions = verification.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise RepositoryError("verification.assertions must be a non-empty list")
        if any(not isinstance(assertion, str) for assertion in assertions):
            raise RepositoryError("verification assertions must be strings")
        try:
            verifier = get_verifier(verifier_name)
            experiment = verification.get("experiment", verifier.default_experiment)
            verifier.validate(experiment, verification["request"], assertions)
        except (TypeError, ValueError, VerifierError) as exc:
            raise RepositoryError(f"Invalid verification request: {exc}") from exc

    def claim_path(self, claim_id: str) -> Path:
        return (
            self.root / "claims" / f"{_validate_identifier(claim_id, 'claim ID')}.yaml"
        )

    def model_path(self, model_id: str) -> Path:
        return (
            self.root / "models" / f"{_validate_identifier(model_id, 'model ID')}.yaml"
        )

    def study_path(self, study_id: str) -> Path:
        return (
            self.root
            / "studies"
            / f"{_validate_identifier(study_id, 'study ID')}.yaml"
        )

    def evidence_path(self, evidence_id: str) -> Path:
        identifier = _validate_identifier(evidence_id, "evidence ID")
        return self.root / "evidence" / f"{identifier}.json"

    def review_path(self, review_id: str) -> Path:
        identifier = _validate_identifier(review_id, "review ID")
        return self.root / "reviews" / f"{identifier}.json"

    def load_claim(self, claim_id: str) -> dict[str, Any]:
        path = self.claim_path(claim_id)
        if not path.exists():
            raise RepositoryError(f"Unknown claim: {claim_id}")
        return self.load_yaml(path)

    def load_model(self, model_id: str) -> dict[str, Any]:
        path = self.model_path(model_id)
        if not path.exists():
            raise RepositoryError(f"Unknown model: {model_id}")
        return self.load_yaml(path)

    def load_study(self, study_id: str) -> dict[str, Any]:
        path = self.study_path(study_id)
        if not path.exists():
            raise RepositoryError(f"Unknown study: {study_id}")
        return self.load_yaml(path)

    def next_evidence_id(self) -> str:
        config = self._load_config()
        evidence_id = f"EV-{config['next_evidence']:06d}"
        config["next_evidence"] += 1
        self._save_config(config)
        return evidence_id

    def next_review_id(self) -> str:
        config = self._load_config()
        next_review = config.get("next_review", 1)
        review_id = f"RV-{next_review:06d}"
        config["next_review"] = next_review + 1
        self._save_config(config)
        return review_id

    def evidence_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        records = []
        for path in sorted((self.root / "evidence").glob("EV-*.json")):
            report = self.audit_evidence(path)
            if not report["valid"]:
                continue
            record = report["record"]
            if record.get("claim", {}).get("id") == claim_id:
                records.append(record)
        return records

    def claim_graph(self) -> dict[str, Any]:
        nodes = []
        edges = []
        status_cache: dict[str, str] = {}
        for path in sorted((self.root / "claims").glob("GS-*.yaml")):
            claim = self.load_yaml(path)
            claim_id = claim["id"]
            dependencies = claim.get("depends_on", [])
            nodes.append(
                {
                    "id": claim_id,
                    "kind": claim.get("kind", "proposition"),
                    "title": claim["title"],
                    "status": self._claim_status(claim_id, status_cache),
                    "dependency_report": self.dependency_report(
                        claim_id, status_cache
                    ),
                }
            )
            edges.extend(
                {"from": dependency, "to": claim_id} for dependency in dependencies
            )
        return {"nodes": nodes, "edges": edges}

    def audit_evidence(self, path: Path) -> dict[str, Any]:
        """Validate one evidence record before allowing it to affect status."""
        errors: list[str] = []
        warnings: list[str] = []
        record: dict[str, Any] = {}
        try:
            loaded = json.loads(path.read_text())
            if not isinstance(loaded, dict):
                raise TypeError("evidence root must be an object")
            record = loaded
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            return {
                "path": path.relative_to(self.root).as_posix(),
                "id": path.stem,
                "valid": False,
                "authenticated": False,
                "errors": [f"invalid JSON: {exc}"],
                "warnings": [],
                "record": {},
            }

        required = {
            "schema_version",
            "id",
            "classification",
            "claim",
            "model",
            "verification",
            "artifact",
            "environment",
            "environment_sha256",
        }
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"missing fields: {', '.join(missing)}")
        if record.get("schema_version") != "gitscience-evidence-v1":
            errors.append("unsupported schema_version")
        if record.get("id") != path.stem:
            errors.append("evidence ID does not match filename")
        try:
            evidence_commit = self.committed_revision(path)
        except RepositoryError as exc:
            evidence_commit = None
            errors.append(str(exc))

        claim = record.get("claim")
        model = record.get("model")
        verification = record.get("verification")
        artifact = record.get("artifact")
        environment = record.get("environment")
        dependencies = record.get("dependencies", [])
        if not isinstance(claim, dict):
            errors.append("claim reference must be an object")
            claim = {}
        if not isinstance(model, dict):
            errors.append("model reference must be an object")
            model = {}
        if not isinstance(verification, dict):
            errors.append("verification must be an object")
            verification = {}
        if not isinstance(artifact, dict):
            errors.append("artifact reference must be an object")
            artifact = {}
        if not isinstance(environment, dict):
            errors.append("environment must be an object")
            environment = {}
        if not isinstance(dependencies, list) or not all(
            isinstance(dependency, dict) for dependency in dependencies
        ):
            errors.append("dependencies must be a list of references")
            dependencies = []

        self._audit_record_reference("claim", claim, errors, warnings)
        self._audit_record_reference("model", model, errors, warnings)
        for dependency in dependencies:
            self._audit_record_reference("claim", dependency, errors, warnings)

        artifact_path = self._safe_record_path(
            artifact.get("path"), "artifacts", errors
        )
        if artifact_path is not None:
            if not artifact_path.exists():
                errors.append("artifact file is missing")
            else:
                if artifact.get("sha256") != self.sha256(artifact_path):
                    errors.append("artifact SHA-256 does not match")
                try:
                    artifact_commit = self.committed_revision(artifact_path)
                    if evidence_commit and artifact_commit != evidence_commit:
                        errors.append(
                            "evidence and artifact were not committed together"
                        )
                except RepositoryError as exc:
                    errors.append(str(exc))
                self._audit_artifact_content(artifact_path, verification, errors)

        if record.get("environment_sha256") != digest_json(environment):
            errors.append("environment SHA-256 does not match")
        evaluations = verification.get("evaluations")
        if not isinstance(evaluations, list) or not all(
            isinstance(evaluation, dict) for evaluation in evaluations
        ):
            errors.append("verification evaluations must be a list of objects")
        else:
            assertions = verification.get("assertions")
            evaluated = [evaluation.get("assertion") for evaluation in evaluations]
            if assertions != evaluated:
                errors.append("evaluations do not match declared assertions")
            for evaluation in evaluations:
                if evaluation.get("passes") not in {True, False, None}:
                    errors.append("evaluation passes value must be boolean or null")
            success_classification = (
                "proving"
                if verification.get("evidence_kind") == "formal_proof"
                else "corroborating"
            )
            derived = classification_from_evaluations(
                evaluations, success=success_classification
            )
            if record.get("classification") != derived:
                errors.append("stored classification disagrees with evaluations")

        recorded_verifier = environment.get("verifier")
        if not isinstance(recorded_verifier, dict) or (
            recorded_verifier.get("name") != verification.get("verifier")
            or recorded_verifier.get("version") != verification.get("verifier_version")
        ):
            errors.append("environment verifier identity disagrees with verification")

        authentication = record.get("authentication")
        authenticated = False
        if authentication is not None and authentication != {
            "method": "none",
            "authenticated": False,
        }:
            errors.append("unsupported or unverifiable authentication claim")
        warnings.append("evidence is not cryptographically authenticated")

        claim_id = claim.get("id")
        if isinstance(claim_id, str):
            try:
                current_claim = self.load_claim(claim_id)
                current_verification = current_claim.get("verification", {})
                current_verifier = current_verification.get(
                    "verifier", current_verification.get("backend")
                )
                evidence_contract = {
                    "verifier": verification.get("verifier"),
                    "experiment": verification.get("experiment", "point_symmetry"),
                    "request": verification.get("request"),
                    "assertions": verification.get("assertions"),
                }
                claim_contract = {
                    "verifier": current_verifier,
                    "experiment": current_verification.get(
                        "experiment", "point_symmetry"
                    ),
                    "request": current_verification.get("request"),
                    "assertions": current_verification.get("assertions"),
                }
                if (
                    claim.get("sha256") == self.sha256(self.claim_path(claim_id))
                    and evidence_contract != claim_contract
                ):
                    errors.append("evidence contract disagrees with current claim")
                if claim.get("sha256") == self.sha256(self.claim_path(claim_id)):
                    current_dependencies = current_claim.get(
                        "dependency_revisions", []
                    )
                    if dependencies != current_dependencies:
                        errors.append(
                            "evidence dependency revisions disagree with current claim"
                        )
            except RepositoryError as exc:
                errors.append(str(exc))

        return {
            "path": path.relative_to(self.root).as_posix(),
            "id": record.get("id", path.stem),
            "valid": not errors,
            "authenticated": authenticated,
            "errors": errors,
            "warnings": warnings,
            "record": record,
        }

    def audit_all_evidence(self, claim_id: str | None = None) -> list[dict[str, Any]]:
        reports = []
        for path in sorted((self.root / "evidence").glob("EV-*.json")):
            report = self.audit_evidence(path)
            record_claim = report["record"].get("claim", {}).get("id")
            if claim_id is None or record_claim == claim_id:
                reports.append(report)
        return reports

    def _safe_record_path(
        self, value: Any, directory: str, errors: list[str]
    ) -> Path | None:
        if not isinstance(value, str):
            errors.append(f"{directory} path must be a string")
            return None
        candidate = Path(value)
        expected_root = (self.root / directory).resolve()
        resolved = (self.root / candidate).resolve()
        if candidate.is_absolute() or not resolved.is_relative_to(expected_root):
            errors.append(f"{directory} path escapes its repository directory")
            return None
        return resolved

    def _audit_record_reference(
        self,
        kind: str,
        reference: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        path = self._safe_record_path(reference.get("path"), f"{kind}s", errors)
        commit = reference.get("git_commit")
        digest = reference.get("sha256")
        if path is None:
            return
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            errors.append(f"{kind} git_commit is invalid")
            return
        relative = path.relative_to(self.root).as_posix()
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"{kind} is unavailable at its recorded commit")
            return
        import hashlib

        if (
            not isinstance(digest, str)
            or hashlib.sha256(result.stdout).hexdigest() != digest
        ):
            errors.append(f"{kind} SHA-256 does not match its recorded commit")
        if path.exists() and self.sha256(path) != digest:
            warnings.append(f"{kind} evidence refers to an older revision")

    @staticmethod
    def _audit_artifact_content(
        artifact_path: Path, verification: dict[str, Any], errors: list[str]
    ) -> None:
        try:
            result = json.loads(artifact_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"artifact is not valid JSON: {exc}")
            return
        evaluations = verification.get("evaluations")
        if not isinstance(result, dict) or not isinstance(evaluations, list):
            return
        for evaluation in evaluations:
            if not isinstance(evaluation, dict):
                continue
            assertion = evaluation.get("assertion")
            expected = (
                result.get("diagnostics")
                if assertion == "numerical_diagnostics"
                else result.get("claims", {}).get(assertion)
            )
            if evaluation.get("detail") != expected:
                errors.append(f"evaluation detail disagrees with artifact: {assertion}")
                continue
            if assertion == "numerical_diagnostics":
                checks = [
                    value
                    for run_checks in (expected or {}).values()
                    for value in run_checks.values()
                ]
                expected_passes = all(checks) if checks else None
            else:
                expected_passes = (
                    expected.get("passes") if isinstance(expected, dict) else None
                )
            if evaluation.get("passes") != expected_passes:
                errors.append(
                    f"evaluation outcome disagrees with artifact: {assertion}"
                )

    def claim_status(self, claim_id: str) -> str:
        return self._claim_status(claim_id, {})

    def _claim_status(self, claim_id: str, status_cache: dict[str, str]) -> str:
        cached = status_cache.get(claim_id)
        if cached is not None:
            return cached
        dependency_report = self.dependency_report(claim_id, status_cache)
        if dependency_report["stale"]:
            status_cache[claim_id] = "stale"
            return "stale"
        if dependency_report["missing_locks"]:
            status_cache[claim_id] = "blocked"
            return "blocked"
        claim_path = self.claim_path(claim_id)
        current_digest = self.sha256(claim_path)
        records = [
            record
            for record in self.evidence_for_claim(claim_id)
            if record.get("claim", {}).get("sha256") == current_digest
        ]
        classifications = {record.get("classification") for record in records}
        if "contradictory" in classifications:
            base_status = "contested"
        elif "proving" in classifications:
            base_status = "proven"
        elif "corroborating" in classifications:
            claim = self.load_claim(claim_id)
            base_status = (
                "supported" if claim.get("scope") == "general" else "corroborated"
            )
        elif "inconclusive" in classifications:
            base_status = "inconclusive"
        else:
            claim = self.load_claim(claim_id)
            if claim.get("kind") in {"definition", "assumption"}:
                base_status = "declared"
            else:
                base_status = "proposed"
        if dependency_report["conditional"]:
            if base_status in {"proven", "corroborated", "supported"}:
                base_status = f"conditional_{base_status}"
            if base_status == "proposed":
                base_status = "conditional"
        status_cache[claim_id] = base_status
        return base_status

    def committed_revision(self, path: Path) -> str:
        relative = path.relative_to(self.root).as_posix()
        if not path.exists():
            raise RepositoryError(f"Missing record: {relative}")
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode != 0:
            raise RepositoryError(f"Record is not committed: {relative}")
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=self.root,
            check=False,
        )
        if dirty.returncode != 0:
            raise RepositoryError(f"Record has uncommitted changes: {relative}")
        commit = self.git(["log", "-1", "--format=%H", "--", relative])
        if not commit:
            raise RepositoryError(f"Record has no committed revision: {relative}")
        return commit

    @staticmethod
    def sha256(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()
