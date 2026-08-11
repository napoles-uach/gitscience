"""Minimal process bridge from a GitScience dossier to PhysicsIntern's reviewer."""

from __future__ import annotations

import argparse
import importlib.resources
import json
from pathlib import Path


def _extract_result(text: str) -> dict:
    decoder = json.JSONDecoder()
    candidates = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "verdict" in value:
            candidates.append(value)
    if not candidates:
        raise ValueError("PhysicsIntern response contains no structured verdict")
    result = candidates[-1]
    verdict = str(result.get("verdict", "")).upper()
    if verdict not in {"VERIFIED", "REFUTED", "INCONCLUSIVE"}:
        verdict = "INCONCLUSIVE"
    result["verdict"] = verdict
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model")
    args = parser.parse_args()

    from physics_intern.baselines import create_provider_from_config, run_baseline_call
    from physics_intern.core.config import Config

    dossier = json.loads(args.input.read_text())
    prompt_path = importlib.resources.files("physics_intern.agents.reviewer").joinpath(
        "prompt.md"
    )
    system = prompt_path.read_text() + """

## GitScience adapter policy

This is an external, advisory review. Your verdict does not authenticate evidence,
does not promote a claim, and does not alter GitScience status. Review only the
bounded dossier supplied below. Do not request tools or execute code.

The dossier is a canonical claim-state object compiled by deterministic GitScience
code. Preserve its distinctions among formal proof, computational corroboration,
dependency status, provenance, scope, and open obligations. Explicitly identify
what is supported, what remains assumed, and what is not established. Never infer
beyond the recorded conditions and limitations, and cite claim and evidence IDs.
"""
    user_message = (
        "<gitscience-dossier>\n"
        + json.dumps(dossier, indent=2, sort_keys=True)
        + "\n</gitscience-dossier>\n\n"
        + "Interpret the current scientific state. Assess whether its evidence supports "
        + "the claim within the recorded scope, while exposing assumptions, unresolved "
        + "obligations, and possible interpretation gaps. Conclude with the structured "
        + "JSON verdict required by your reviewer prompt."
    )
    config = Config(model=args.model) if args.model else Config()
    provider = create_provider_from_config(config)
    response = run_baseline_call(
        provider,
        config,
        system=system,
        user_message=user_message,
        agent_name="gitscience_reviewer",
    )
    result = _extract_result(response["response_text"])
    result["physics_intern"] = {
        "model": config.model,
        "model_id": config.model_id,
        "provider": config.provider,
        "tokens": response["tokens"],
        "duration_s": response["duration_s"],
        "cost_usd": response["cost_usd"],
        "stop_reason": response["stop_reason"],
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
