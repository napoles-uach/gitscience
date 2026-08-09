"""Plugin contract and discovery for computational verifiers."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any, Protocol


class VerifierError(RuntimeError):
    """Raised when a verifier plugin is unavailable or invalid."""


class VerifierPlugin(Protocol):
    """Runtime contract implemented by installed verifier plugins."""

    name: str
    version: str
    default_experiment: str
    artifact_suffix: str
    evidence_kind: str
    environment_packages: tuple[str, ...]

    def validate(
        self, experiment: str, request: dict[str, Any], assertions: list[str]
    ) -> None: ...

    def run(self, experiment: str, request: dict[str, Any]) -> dict[str, Any]: ...

    def source_paths(self) -> list[Path]: ...


def _entry_points():
    discovered = importlib.metadata.entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group="gitscience.verifiers")
    return discovered.get("gitscience.verifiers", ())


def get_verifier(name: str) -> VerifierPlugin:
    """Load one installed verifier without importing it into the core package."""
    matches = [
        entry_point for entry_point in _entry_points() if entry_point.name == name
    ]
    if not matches:
        available = ", ".join(sorted(point.name for point in _entry_points())) or "none"
        raise VerifierError(
            f"Verifier {name!r} is not installed. Available verifiers: {available}"
        )
    if len(matches) > 1:
        raise VerifierError(f"Multiple verifier plugins are registered as {name!r}")
    try:
        plugin = matches[0].load()
    except Exception as exc:
        raise VerifierError(f"Could not load verifier {name!r}: {exc}") from exc
    if callable(plugin) and not hasattr(plugin, "run"):
        plugin = plugin()
    required = {
        "name",
        "version",
        "default_experiment",
        "artifact_suffix",
        "evidence_kind",
        "environment_packages",
        "validate",
        "run",
        "source_paths",
    }
    missing = sorted(
        attribute for attribute in required if not hasattr(plugin, attribute)
    )
    if missing:
        raise VerifierError(
            f"Verifier {name!r} does not implement: {', '.join(missing)}"
        )
    if plugin.name != name:
        raise VerifierError(
            f"Verifier entry point {name!r} loaded mismatched plugin {plugin.name!r}"
        )
    return plugin
