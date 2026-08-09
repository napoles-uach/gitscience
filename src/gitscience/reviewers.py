"""Plugin contract and discovery for advisory scientific reviewers."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any, Protocol


class ReviewerError(RuntimeError):
    """Raised when an advisory reviewer is unavailable or invalid."""


class ReviewerPlugin(Protocol):
    """Runtime contract implemented by installed reviewer plugins."""

    name: str
    version: str
    environment_packages: tuple[str, ...]

    def run(
        self, dossier: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]: ...

    def source_paths(self) -> list[Path]: ...


def _entry_points():
    discovered = importlib.metadata.entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group="gitscience.reviewers")
    return discovered.get("gitscience.reviewers", ())


def get_reviewer(name: str) -> ReviewerPlugin:
    """Load one advisory reviewer without importing it into the core package."""
    matches = [point for point in _entry_points() if point.name == name]
    if not matches:
        available = ", ".join(sorted(point.name for point in _entry_points())) or "none"
        raise ReviewerError(
            f"Reviewer {name!r} is not installed. Available reviewers: {available}"
        )
    if len(matches) > 1:
        raise ReviewerError(f"Multiple reviewer plugins are registered as {name!r}")
    try:
        plugin = matches[0].load()
    except Exception as exc:
        raise ReviewerError(f"Could not load reviewer {name!r}: {exc}") from exc
    if callable(plugin) and not hasattr(plugin, "run"):
        plugin = plugin()
    required = {"name", "version", "environment_packages", "run", "source_paths"}
    missing = sorted(name for name in required if not hasattr(plugin, name))
    if missing:
        raise ReviewerError(
            f"Reviewer {name!r} does not implement: {', '.join(missing)}"
        )
    if plugin.name != name:
        raise ReviewerError(
            f"Reviewer entry point {name!r} loaded mismatched plugin {plugin.name!r}"
        )
    return plugin
