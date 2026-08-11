"""Non-asymptotic binomial checks for two non-adaptive FMM regimes."""

from __future__ import annotations

from datetime import UTC, datetime
from math import ceil, exp, fsum, lgamma, log
from typing import Any

from .schema import OccupancyRegimeRequest


def _binomial_tail(particles: int, probability: float, capacity: int) -> float:
    """Return P[X > capacity] for X distributed as Binomial(particles, probability)."""
    if capacity >= particles:
        return 0.0
    first = capacity + 1
    log_term = (
        lgamma(particles + 1)
        - lgamma(first + 1)
        - lgamma(particles - first + 1)
        + first * log(probability)
        + (particles - first) * log1p_negative(probability)
    )
    term = exp(log_term)
    terms = [term]
    odds = probability / (1.0 - probability)
    for occupied in range(first, particles):
        term *= (particles - occupied) / (occupied + 1) * odds
        terms.append(term)
        if term == 0.0:
            break
    return min(1.0, fsum(terms))


def log1p_negative(probability: float) -> float:
    """Stable log(1-p) without accepting probabilities outside (0, 1)."""
    if not 0.0 < probability < 1.0:
        raise ValueError("box probability must be between zero and one")
    from math import log1p

    return log1p(-probability)


def _union_bound(particles: int, boxes: int, capacity: int) -> float:
    return min(1.0, boxes * _binomial_tail(particles, 1.0 / boxes, capacity))


def _constant_mean_regime(
    request: OccupancyRegimeRequest, probability_budget: float
) -> dict[str, Any]:
    boxes = max(2, ceil(request.particles / request.constant_mean))
    for capacity in range(request.max_capacity + 1):
        bound = _union_bound(request.particles, boxes, capacity)
        if bound <= probability_budget:
            return _regime_record(request.particles, boxes, capacity, bound)
    raise ValueError("constant-mean capacity exceeds max_capacity")


def _proportional_mean_regime(
    request: OccupancyRegimeRequest, probability_budget: float
) -> dict[str, Any]:
    for capacity in range(1, request.max_capacity + 1):
        boxes = max(2, ceil(request.particles / (request.load_fraction * capacity)))
        bound = _union_bound(request.particles, boxes, capacity)
        if bound <= probability_budget:
            return _regime_record(request.particles, boxes, capacity, bound)
    raise ValueError("proportional-mean capacity exceeds max_capacity")


def _regime_record(
    particles: int, boxes: int, capacity: int, union_bound: float
) -> dict[str, Any]:
    return {
        "boxes": boxes,
        "capacity": capacity,
        "mean_occupancy": particles / boxes,
        "union_bound_bad_probability": union_bound,
        "near_field_slot_pairs": boxes * capacity**2,
    }


def run_occupancy_regime_experiment(values: dict[str, Any]) -> dict[str, Any]:
    """Compare valid constant-mean and proportional-mean occupancy regimes."""
    request = OccupancyRegimeRequest.from_mapping(values)
    probability_budget = request.per_call_bad_probability_budget
    constant = _constant_mean_regime(request, probability_budget)
    proportional = _proportional_mean_regime(request, probability_budget)

    hybrid_capacity = constant["capacity"]
    hybrid_boxes = max(2, ceil(request.particles / max(1, hybrid_capacity)))
    hybrid_bound = _union_bound(request.particles, hybrid_boxes, hybrid_capacity)
    hybrid = _regime_record(
        request.particles, hybrid_boxes, hybrid_capacity, hybrid_bound
    )

    probabilities_valid = all(
        0.0 <= regime["union_bound_bad_probability"] <= 1.0
        for regime in (constant, proportional, hybrid)
    )
    capacities_valid = all(
        0 <= regime["capacity"] <= request.max_capacity
        for regime in (constant, proportional, hybrid)
    )
    claims = {
        "constant_mean_tail_budget": {
            "passes": constant["union_bound_bad_probability"] <= probability_budget,
            "observed": constant["union_bound_bad_probability"],
            "required": probability_budget,
        },
        "proportional_mean_tail_budget": {
            "passes": proportional["union_bound_bad_probability"] <= probability_budget,
            "observed": proportional["union_bound_bad_probability"],
            "required": probability_budget,
        },
        "hybrid_regime_exceeds_tail_budget": {
            "passes": hybrid["union_bound_bad_probability"] > probability_budget,
            "observed": hybrid["union_bound_bad_probability"],
            "required_maximum": probability_budget,
        },
    }
    return {
        "schema_version": "fmm-occupancy-v1",
        "model": "independent-uniform-box-occupancy-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "request": request.to_dict(),
        "per_call_bad_probability_budget": probability_budget,
        "regimes": {
            "constant_mean": constant,
            "proportional_mean": proportional,
            "inconsistent_hybrid": hybrid,
        },
        "claims": claims,
        "diagnostics": {
            "probabilities": {"valid": probabilities_valid},
            "capacities": {"within_configured_limit": capacities_valid},
        },
    }
