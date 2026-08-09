"""Tests for the trusted Kwant transport adapter (without requiring Kwant)."""

import pytest

from gitscience_kwant import TransportRequest, run_transport_experiment


def _fake_solver(request, tau, soc=None):
    effective_soc = request.soc if soc is None else soc
    polarization = 0.0 if effective_soc == 0 else 0.2 * tau
    return {
        "tau": tau,
        "soc": effective_soc,
        "energy": request.energy,
        "transmission": 1.5 + tau**2,
        "spin_transmission_minus_x": 0.75 + 0.5 * tau**2,
        "spin_transmission_plus_x": 0.75 + 0.5 * tau**2,
        "polarization_x": polarization,
        "transmission_decomposition_residual": 0.0,
        "hermiticity_residual": 1e-14,
        "unitarity_residual": 2e-14,
        "lead_block_nmodes": [[1, 1], [1, 1]],
        "hamiltonian_dimension": 40,
    }


def test_request_rejects_unknown_and_oversized_inputs():
    with pytest.raises(ValueError, match="Unknown"):
        TransportRequest.from_mapping(
            {"width": 4, "length": 8, "energy": 1.0, "tau": 0.1, "code": "x"}
        )
    with pytest.raises(ValueError, match="12000"):
        TransportRequest.from_mapping(
            {"width": 80, "length": 300, "energy": 1.0, "tau": 0.1}
        )


def test_experiment_evaluates_symmetries_and_controls():
    result = run_transport_experiment(
        {"width": 4, "length": 10, "energy": 1.0, "tau": 0.25},
        solver=_fake_solver,
    )

    assert set(result["runs"]) == {
        "plus_tau",
        "minus_tau",
        "zero_tau",
        "zero_soc",
    }
    assert result["claims"]["transmission_even_in_tau"]["passes"] is True
    assert result["claims"]["polarization_x_odd_in_tau"]["passes"] is True
    assert result["claims"]["zero_twist_polarization"]["passes"] is True
    assert result["claims"]["zero_soc_polarization"]["passes"] is True
    assert all(check["hermitian"] for check in result["diagnostics"].values())
    assert all(check["unitary"] for check in result["diagnostics"].values())
    assert all(
        check["spin_decomposition_consistent"]
        for check in result["diagnostics"].values()
    )
    assert all(check["lead_modes_matched"] for check in result["diagnostics"].values())
