"""Plugin contract for agents that propose formal verification obligations."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any, Protocol


class FormalizerError(RuntimeError):
    """Raised when a formalization agent is unavailable or invalid."""


class FormalizerPlugin(Protocol):
    """Runtime contract implemented by installed formalization agents."""

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
        return discovered.select(group="gitscience.formalizers")
    return discovered.get("gitscience.formalizers", ())


def get_formalizer(name: str) -> FormalizerPlugin:
    """Load one formalization agent without importing it into the core package."""
    matches = [point for point in _entry_points() if point.name == name]
    if not matches:
        available = ", ".join(sorted(point.name for point in _entry_points())) or "none"
        raise FormalizerError(
            f"Formalizer {name!r} is not installed. Available formalizers: {available}"
        )
    if len(matches) > 1:
        raise FormalizerError(f"Multiple formalizer plugins are registered as {name!r}")
    try:
        plugin = matches[0].load()
    except Exception as exc:
        raise FormalizerError(f"Could not load formalizer {name!r}: {exc}") from exc
    if callable(plugin) and not hasattr(plugin, "run"):
        plugin = plugin()
    required = {"name", "version", "environment_packages", "run", "source_paths"}
    missing = sorted(field for field in required if not hasattr(plugin, field))
    if missing:
        raise FormalizerError(
            f"Formalizer {name!r} does not implement: {', '.join(missing)}"
        )
    if plugin.name != name:
        raise FormalizerError(
            f"Formalizer entry point {name!r} loaded mismatched plugin {plugin.name!r}"
        )
    return plugin
