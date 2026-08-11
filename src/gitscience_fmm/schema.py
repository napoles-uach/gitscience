"""Validated input schema for independent occupancy-tail experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class OccupancyRegimeRequest:
    """Finite independent-particle instance used to compare box regimes."""

    particles: int
    calls: int
    tail_error_budget: float
    constant_mean: float = 1.0
    load_fraction: float = 0.5
    max_capacity: int = 512

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> OccupancyRegimeRequest:
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown FMM occupancy parameters: {', '.join(unknown)}")
        try:
            request = cls(**values)
        except TypeError as exc:
            raise ValueError(f"Invalid FMM occupancy request: {exc}") from exc
        request.validate()
        return request

    def validate(self) -> None:
        for name in ("particles", "calls", "max_capacity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not 16 <= self.particles <= 100_000:
            raise ValueError("particles must be between 16 and 100000")
        if not 1 <= self.calls <= 10_000:
            raise ValueError("calls must be between 1 and 10000")
        if not 2 <= self.max_capacity <= 4096:
            raise ValueError("max_capacity must be between 2 and 4096")

        for name in ("tail_error_budget", "constant_mean", "load_fraction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a finite number")
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if not 1e-12 <= self.tail_error_budget < 1:
            raise ValueError("tail_error_budget must be between 1e-12 and one")
        if not 0.1 <= self.constant_mean <= 8:
            raise ValueError("constant_mean must be between 0.1 and 8")
        if not 0.05 <= self.load_fraction <= 0.8:
            raise ValueError("load_fraction must be between 0.05 and 0.8")

    @property
    def per_call_bad_probability_budget(self) -> float:
        return (self.tail_error_budget / (2 * self.calls)) ** 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
