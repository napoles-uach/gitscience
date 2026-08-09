"""Deterministic integrity helpers shared by verification and auditing."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def digest_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def classification_from_evaluations(
    evaluations: list[dict[str, Any]], success: str = "corroborating"
) -> str:
    passes = [evaluation.get("passes") for evaluation in evaluations]
    if any(value is False for value in passes):
        return "contradictory"
    if not passes or any(value is not True for value in passes):
        return "inconclusive"
    return success
