"""Validated input schema for the Kwant transport prototype."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class TransportRequest:
    """Parameters accepted by the trusted twisted-nanoribbon solver."""

    width: int
    length: int
    energy: float
    tau: float
    hopping: float = 1.0
    soc: float = 0.1
    onsite: float = 0.0
    compare_opposite_tau: bool = True
    check_zero_twist: bool = True
    check_soc_zero: bool = True
    symmetry_tolerance: float = 1e-7
    numerical_tolerance: float = 1e-9

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> TransportRequest:
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - allowed)
        if unknown:
            unknown_fields = ", ".join(unknown)
            raise ValueError(f"Unknown Kwant transport parameters: {unknown_fields}")
        try:
            request = cls(**values)
        except TypeError as exc:
            raise ValueError(f"Invalid Kwant transport request: {exc}") from exc
        request.validate()
        return request

    def validate(self) -> None:
        if isinstance(self.width, bool) or not isinstance(self.width, int):
            raise TypeError("width must be an integer")
        if isinstance(self.length, bool) or not isinstance(self.length, int):
            raise TypeError("length must be an integer")
        if not 2 <= self.width <= 80:
            raise ValueError("width must be between 2 and 80")
        if not 2 <= self.length <= 300:
            raise ValueError("length must be between 2 and 300")
        if self.width * self.length > 12_000:
            raise ValueError("width * length must not exceed 12000 sites")

        numeric = {
            "energy": self.energy,
            "tau": self.tau,
            "hopping": self.hopping,
            "soc": self.soc,
            "onsite": self.onsite,
            "symmetry_tolerance": self.symmetry_tolerance,
            "numerical_tolerance": self.numerical_tolerance,
        }
        for name, value in numeric.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a finite number")
            if not isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
        if self.hopping <= 0:
            raise ValueError("hopping must be positive")
        if self.soc < 0:
            raise ValueError("soc must be non-negative")
        if self.symmetry_tolerance <= 0 or self.numerical_tolerance <= 0:
            raise ValueError("tolerances must be positive")

        for name in ("compare_opposite_tau", "check_zero_twist", "check_soc_zero"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
