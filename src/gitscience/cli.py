"""Command-line interface for the local GitScience MVP."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from .repository import GitScienceRepository, RepositoryError
from .review import ReviewError, inspect_review, review_claim
from .reviewers import ReviewerError
from .state import compile_claim_state, explain_claim_state
from .verification import VerificationError, inspect_claim, verify_claim


def _repository(args: argparse.Namespace) -> GitScienceRepository:
    start = args.directory if getattr(args, "directory", None) else Path.cwd()
    return GitScienceRepository.discover(start)


def _print_yaml(value: dict) -> None:
    print(yaml.safe_dump(value, sort_keys=False, allow_unicode=True).rstrip())


def _build_claim_source(args: argparse.Namespace) -> Path:
    if args.source:
        return args.source
    if not args.topic or not args.model or not args.request:
        raise RepositoryError(
            "claim create requires --from, or --topic, --model and --request"
        )
    title = args.title or input("Title: ").strip()
    statement = args.statement or input("Hypothesis: ").strip()
    if not title or not statement:
        raise RepositoryError("Claim title and statement cannot be empty")
    request = GitScienceRepository.load_yaml(args.request)
    assertions = args.assertion or [
        "transmission_even_in_tau",
        "numerical_diagnostics",
    ]
    claim = {
        "title": title,
        "statement": statement,
        "topic": args.topic,
        "model": args.model,
        "scope": args.scope,
        "conditions": args.condition or [],
        "verification": {
            "verifier": "kwant_transport",
            "request": request,
            "assertions": assertions,
        },
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".gitscience-claim.yaml", delete=False
    ) as temporary:
        yaml.safe_dump(claim, temporary, sort_keys=False, allow_unicode=True)
        return Path(temporary.name)


def _cmd_init(args: argparse.Namespace) -> int:
    name = args.name or args.path.name
    repo = GitScienceRepository.init(args.path, name)
    print(f"Initialized GitScience repository: {repo.root}")
    return 0


def _cmd_topic_create(args: argparse.Namespace) -> int:
    topic = _repository(args).create_topic(args.name, args.code)
    print(f"Created topic {topic['code']}: {topic['name']}")
    return 0


def _cmd_topic_list(args: argparse.Namespace) -> int:
    repo = _repository(args)
    for path in sorted((repo.root / "topics").glob("*.yaml")):
        topic = repo.load_yaml(path)
        print(f"{topic['code']}\t{topic['name']}")
    return 0


def _cmd_model_create(args: argparse.Namespace) -> int:
    model = _repository(args).create_model(args.model_id, args.source)
    print(f"Created model {model['id']}")
    return 0


def _cmd_claim_create(args: argparse.Namespace) -> int:
    generated = args.source is None
    source = _build_claim_source(args)
    try:
        claim = _repository(args).create_claim(source)
    finally:
        if generated and source.exists():
            source.unlink()
    print(f"Created claim {claim['id']}: {claim['title']}")
    return 0


def _cmd_claim_show(args: argparse.Namespace) -> int:
    repo = _repository(args)
    claim = repo.load_claim(args.claim_id)
    claim["derived_status"] = repo.claim_status(args.claim_id)
    _print_yaml(claim)
    return 0


def _cmd_claim_list(args: argparse.Namespace) -> int:
    repo = _repository(args)
    for path in sorted((repo.root / "claims").glob("GS-*.yaml")):
        claim = repo.load_yaml(path)
        status = repo.claim_status(claim["id"])
        kind = claim.get("kind", "proposition")
        print(f"{claim['id']}\t{status}\t{kind}\t{claim['title']}")
    return 0


def _cmd_claim_log(args: argparse.Namespace) -> int:
    repo = _repository(args)
    path = repo.claim_path(args.claim_id).relative_to(repo.root).as_posix()
    print(repo.git(["log", "--oneline", "--decorate", "--", path]))
    return 0


def _cmd_claim_graph(args: argparse.Namespace) -> int:
    graph = _repository(args).claim_graph()
    for node in graph["nodes"]:
        print(f"{node['id']} [{node['kind']}, {node['status']}] {node['title']}")
        dependencies = [
            edge["from"] for edge in graph["edges"] if edge["to"] == node["id"]
        ]
        if dependencies:
            print(f"  depends on: {', '.join(dependencies)}")
    return 0


def _cmd_claim_relock(args: argparse.Namespace) -> int:
    claim = _repository(args).lock_dependencies(args.claim_id)
    locked = [item["id"] for item in claim["dependency_revisions"]]
    print(f"Locked {args.claim_id} dependencies: {', '.join(locked) or 'none'}")
    print("Commit the updated claim before verification.")
    return 0


def _cmd_claim_obligations(args: argparse.Namespace) -> int:
    repo = _repository(args)
    graph = repo.claim_graph()
    for node in graph["nodes"]:
        report = node["dependency_report"]
        print(f"{node['id']}\t{node['status']}\t{node['kind']}\t{node['title']}")
        for reason in report["reasons"]:
            print(f"  obligation: {reason}")
    return 0


def _cmd_claim_state(args: argparse.Namespace) -> int:
    state = compile_claim_state(_repository(args), args.claim_id)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        _print_yaml(state)
    return 0


def _cmd_claim_explain(args: argparse.Namespace) -> int:
    state = compile_claim_state(_repository(args), args.claim_id)
    print(explain_claim_state(state))
    return 0


def _cmd_verify_inspect(args: argparse.Namespace) -> int:
    _print_yaml(inspect_claim(_repository(args), args.claim_id))
    return 0


def _cmd_verify_run(args: argparse.Namespace) -> int:
    repo = _repository(args)
    generated_paths = [".gitscience/config.json"]
    results = []
    for claim_id in args.claim_ids:
        evidence = verify_claim(repo, claim_id)
        results.append((claim_id, evidence))
        generated_paths.extend(
            [
                repo.evidence_path(evidence["id"]).relative_to(repo.root).as_posix(),
                evidence["artifact"]["path"],
            ]
        )
    if args.commit_evidence:
        repo.git(["add", "--", *generated_paths])
        message = "Record verification evidence for " + ", ".join(args.claim_ids)
        repo.git(["commit", "--only", "-m", message, "--", *generated_paths])
    for claim_id, evidence in results:
        print(
            f"{claim_id}: {evidence['classification']} "
            f"({evidence['id']}, {evidence['artifact']['path']})"
        )
    return 0


def _cmd_evidence_show(args: argparse.Namespace) -> int:
    path = _repository(args).evidence_path(args.evidence_id)
    if not path.exists():
        raise RepositoryError(f"Unknown evidence: {args.evidence_id}")
    print(json.dumps(json.loads(path.read_text()), indent=2, sort_keys=True))
    return 0


def _cmd_evidence_list(args: argparse.Namespace) -> int:
    repo = _repository(args)
    for path in sorted((repo.root / "evidence").glob("EV-*.json")):
        report = repo.audit_evidence(path)
        evidence = report["record"]
        claim_id = evidence.get("claim", {}).get("id", "?")
        if args.claim and claim_id != args.claim:
            continue
        classification = (
            evidence.get("classification", "?") if report["valid"] else "invalid"
        )
        print(f"{evidence.get('id', path.stem)}\t{claim_id}\t{classification}")
    return 0


def _cmd_review_inspect(args: argparse.Namespace) -> int:
    _print_yaml(inspect_review(_repository(args), args.claim_id, args.reviewer))
    return 0


def _cmd_review_run(args: argparse.Namespace) -> int:
    repo = _repository(args)
    options = {"timeout": args.timeout}
    if args.model:
        options["model"] = args.model
    review = review_claim(repo, args.claim_id, args.reviewer, options)
    paths = [
        ".gitscience/config.json",
        repo.review_path(review["id"]).relative_to(repo.root).as_posix(),
        review["artifact"]["path"],
    ]
    if args.commit_review:
        repo.git(["add", "--", *paths])
        repo.git(
            [
                "commit",
                "--only",
                "-m",
                f"Record advisory review for {args.claim_id}",
                "--",
                *paths,
            ]
        )
    print(
        f"{args.claim_id}: {review['verdict']} advisory review "
        f"({review['id']}, status unchanged)"
    )
    return 0


def _cmd_review_show(args: argparse.Namespace) -> int:
    path = _repository(args).review_path(args.review_id)
    if not path.exists():
        raise RepositoryError(f"Unknown review: {args.review_id}")
    print(json.dumps(json.loads(path.read_text()), indent=2, sort_keys=True))
    return 0


def _cmd_review_list(args: argparse.Namespace) -> int:
    repo = _repository(args)
    for path in sorted((repo.root / "reviews").glob("RV-*.json")):
        review = json.loads(path.read_text())
        claim_id = review.get("claim", {}).get("id", "?")
        if args.claim and args.claim != claim_id:
            continue
        print(
            f"{review.get('id', path.stem)}\t{claim_id}\t"
            f"{review.get('verdict', '?')}\tadvisory"
        )
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    reports = _repository(args).audit_all_evidence(args.claim)
    invalid = False
    for report in reports:
        status = "integrity-valid" if report["valid"] else "INVALID"
        print(f"{report['id']}\t{status}\t{report['path']}")
        for error in report["errors"]:
            print(f"  error: {error}")
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        invalid = (
            invalid
            or not report["valid"]
            or (args.require_authenticated and not report["authenticated"])
        )
    if not reports:
        print("No evidence records found.")
    return 1 if invalid else 0


def _cmd_status(args: argparse.Namespace) -> int:
    print(_repository(args).git(["status", "--short"]))
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    print(_repository(args).git(["diff", "--", "."]))
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    print(
        _repository(args).git(
            ["log", "--oneline", "--decorate", "-n", str(args.max_count)]
        )
    )
    return 0


def _cmd_commit(args: argparse.Namespace) -> int:
    repo = _repository(args)
    repo.git(["add", "-A"])
    repo.git(["commit", "-m", args.message])
    print(repo.git(["log", "-1", "--oneline"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitscience",
        description="Version scientific claims and trusted computational evidence.",
    )
    parser.add_argument(
        "-C",
        "--directory",
        type=Path,
        help="Run as if GitScience was started in this directory.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Initialize a scientific repository.")
    init.add_argument("path", type=Path)
    init.add_argument("--name")
    init.set_defaults(handler=_cmd_init)

    topic = commands.add_parser("topic", help="Manage scientific topics.")
    topic_commands = topic.add_subparsers(dest="topic_command", required=True)
    topic_create = topic_commands.add_parser("create")
    topic_create.add_argument("name")
    topic_create.add_argument("--code", required=True)
    topic_create.set_defaults(handler=_cmd_topic_create)
    topic_list = topic_commands.add_parser("list")
    topic_list.set_defaults(handler=_cmd_topic_list)

    model = commands.add_parser("model", help="Manage model definitions.")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    model_create = model_commands.add_parser("create")
    model_create.add_argument("model_id")
    model_create.add_argument("--from", dest="source", type=Path, required=True)
    model_create.set_defaults(handler=_cmd_model_create)

    claim = commands.add_parser("claim", help="Manage scientific claims.")
    claim_commands = claim.add_subparsers(dest="claim_command", required=True)
    claim_create = claim_commands.add_parser("create")
    claim_create.add_argument("--from", dest="source", type=Path)
    claim_create.add_argument("--topic")
    claim_create.add_argument("--model")
    claim_create.add_argument("--title")
    claim_create.add_argument("--statement")
    claim_create.add_argument("--scope", default="numerical_instance")
    claim_create.add_argument("--request", type=Path)
    claim_create.add_argument("--assertion", action="append")
    claim_create.add_argument("--condition", action="append")
    claim_create.set_defaults(handler=_cmd_claim_create)
    claim_list = claim_commands.add_parser("list")
    claim_list.set_defaults(handler=_cmd_claim_list)
    claim_show = claim_commands.add_parser("show")
    claim_show.add_argument("claim_id")
    claim_show.set_defaults(handler=_cmd_claim_show)
    claim_log = claim_commands.add_parser("log")
    claim_log.add_argument("claim_id")
    claim_log.set_defaults(handler=_cmd_claim_log)
    claim_graph = claim_commands.add_parser("graph")
    claim_graph.set_defaults(handler=_cmd_claim_graph)
    claim_relock = claim_commands.add_parser("relock")
    claim_relock.add_argument("claim_id")
    claim_relock.set_defaults(handler=_cmd_claim_relock)
    claim_obligations = claim_commands.add_parser("obligations")
    claim_obligations.set_defaults(handler=_cmd_claim_obligations)
    claim_state = claim_commands.add_parser(
        "state", help="Compile the canonical state of one claim."
    )
    claim_state.add_argument("claim_id")
    claim_state.add_argument("--json", action="store_true")
    claim_state.set_defaults(handler=_cmd_claim_state)
    claim_explain = claim_commands.add_parser(
        "explain", help="Render a concise human view of one claim state."
    )
    claim_explain.add_argument("claim_id")
    claim_explain.set_defaults(handler=_cmd_claim_explain)

    verify = commands.add_parser("verify", help="Inspect or run trusted verification.")
    verify_commands = verify.add_subparsers(dest="verify_command", required=True)
    verify_inspect = verify_commands.add_parser("inspect")
    verify_inspect.add_argument("claim_id")
    verify_inspect.set_defaults(handler=_cmd_verify_inspect)
    verify_run = verify_commands.add_parser("run")
    verify_run.add_argument("claim_ids", nargs="+")
    verify_run.add_argument(
        "--commit-evidence", action="store_true", help=argparse.SUPPRESS
    )
    verify_run.set_defaults(handler=_cmd_verify_run)

    evidence = commands.add_parser("evidence", help="Inspect evidence records.")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_show = evidence_commands.add_parser("show")
    evidence_show.add_argument("evidence_id")
    evidence_show.set_defaults(handler=_cmd_evidence_show)
    evidence_list = evidence_commands.add_parser("list")
    evidence_list.add_argument("--claim")
    evidence_list.set_defaults(handler=_cmd_evidence_list)

    review = commands.add_parser("review", help="Run advisory scientific review.")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_inspect = review_commands.add_parser("inspect")
    review_inspect.add_argument("claim_id")
    review_inspect.add_argument("--with", dest="reviewer", required=True)
    review_inspect.set_defaults(handler=_cmd_review_inspect)
    review_run = review_commands.add_parser("run")
    review_run.add_argument("claim_id")
    review_run.add_argument("--with", dest="reviewer", required=True)
    review_run.add_argument("--model")
    review_run.add_argument("--timeout", type=int, default=300)
    review_run.add_argument("--commit-review", action="store_true", help=argparse.SUPPRESS)
    review_run.set_defaults(handler=_cmd_review_run)
    review_show = review_commands.add_parser("show")
    review_show.add_argument("review_id")
    review_show.set_defaults(handler=_cmd_review_show)
    review_list = review_commands.add_parser("list")
    review_list.add_argument("--claim")
    review_list.set_defaults(handler=_cmd_review_list)

    audit = commands.add_parser("audit", help="Validate evidence integrity.")
    audit.add_argument("--claim")
    audit.add_argument(
        "--require-authenticated",
        action="store_true",
        help="Fail unless every selected evidence record has a verified signature.",
    )
    audit.set_defaults(handler=_cmd_audit)

    status = commands.add_parser("status", help="Show repository changes.")
    status.set_defaults(handler=_cmd_status)
    diff = commands.add_parser("diff", help="Show unstaged scientific changes.")
    diff.set_defaults(handler=_cmd_diff)
    log = commands.add_parser("log", help="Show recent repository commits.")
    log.add_argument("-n", "--max-count", type=int, default=10)
    log.set_defaults(handler=_cmd_log)
    commit = commands.add_parser("commit", help="Commit all repository changes.")
    commit.add_argument("-m", "--message", required=True)
    commit.set_defaults(handler=_cmd_commit)
    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """Map concise verify/review syntax to explicit subcommands."""
    normalized = list(argv)
    try:
        verify_index = normalized.index("verify")
    except ValueError:
        pass
    else:
        next_index = verify_index + 1
        if next_index < len(normalized) and normalized[next_index] not in {
            "inspect",
            "run",
            "-h",
            "--help",
        }:
            normalized[next_index:next_index] = ["run", "--commit-evidence"]
    try:
        review_index = normalized.index("review")
    except ValueError:
        pass
    else:
        next_index = review_index + 1
        if next_index < len(normalized) and normalized[next_index] not in {
            "inspect",
            "run",
            "show",
            "list",
            "-h",
            "--help",
        }:
            normalized[next_index:next_index] = ["run", "--commit-review"]
    return normalized


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(_normalize_argv(raw_argv))
    try:
        return args.handler(args)
    except (
        RepositoryError,
        ReviewError,
        ReviewerError,
        VerificationError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def entrypoint() -> None:
    raise SystemExit(main())
