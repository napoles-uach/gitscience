"""Tests for the trusted small-twist scaling experiment."""

import pytest

from gitscience_kwant import (
    SmallTwistRequest,
    run_small_twist_experiment,
)


def _solver(request, tau, soc=None):
    transmission = 4.0 - 10.0 * tau**2
    polarization = 0.05 * tau
    spin_plus = 0.5 * transmission * (1.0 + polarization)
    spin_minus = 0.5 * transmission * (1.0 - polarization)
    return {
        "tau": tau,
        "transmission": transmission,
        "polarization_x": polarization,
        "spin_transmission_plus_x": spin_plus,
        "spin_transmission_minus_x": spin_minus,
        "transmission_decomposition_residual": 0.0,
        "hermiticity_residual": 0.0,
        "unitarity_residual": 1e-14,
        "lead_block_nmodes": [[2, 2], [2, 2]],
    }


def _request():
    return {
        "width": 8,
        "length": 24,
        "energy": 1.0,
        "tau_values": [0.0, 0.01, 0.02, 0.03, 0.04],
        "hopping": 1.0,
        "soc": 0.1,
        "linearity_tolerance": 0.06,
        "quadratic_tolerance": 0.05,
    }


def test_exact_small_twist_scaling_passes():
    result = run_small_twist_experiment(_request(), solver=_solver)

    px = result["claims"]["polarization_linear_in_small_twist"]
    transmission = result["claims"]["transmission_quadratic_in_small_twist"]
    assert px["passes"] is True
    assert px["slope"] == pytest.approx(0.05)
    assert px["relative_max_residual"] < 1e-12
    assert transmission["passes"] is True
    assert transmission["quadratic_coefficient"] == pytest.approx(-10.0)
    assert len(result["runs"]) == 9
    assert all(all(checks.values()) for checks in result["diagnostics"].values())


def test_nonlinear_polarization_fails_linearity_claim():
    def nonlinear_solver(request, tau, soc=None):
        run = _solver(request, tau, soc)
        run["polarization_x"] = 0.05 * tau + 100.0 * tau**3
        return run

    result = run_small_twist_experiment(_request(), solver=nonlinear_solver)

    assert result["claims"]["polarization_linear_in_small_twist"]["passes"] is False


def test_sweep_requires_sorted_unique_values_starting_at_zero():
    values = _request()
    values["tau_values"] = [0.0, 0.02, 0.01, 0.04]
    with pytest.raises(ValueError, match="sorted and unique"):
        SmallTwistRequest.from_mapping(values)


def test_sweep_rejects_code_or_unknown_parameters():
    values = _request()
    values["code"] = "print('no')"
    with pytest.raises(ValueError, match="Unknown"):
        SmallTwistRequest.from_mapping(values)
