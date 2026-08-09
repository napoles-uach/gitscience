"""Optional integration test executed when Kwant is installed."""

import pytest

pytest.importorskip("kwant")

from gitscience_kwant import run_transport_experiment


def test_reference_twisted_ribbon_point():
    result = run_transport_experiment(
        {
            "width": 8,
            "length": 24,
            "energy": 1.0,
            "tau": 0.08,
            "hopping": 1.0,
            "soc": 0.1,
            "onsite": 0.0,
        }
    )

    plus = result["runs"]["plus_tau"]
    assert plus["transmission"] == pytest.approx(3.8566995151, rel=1e-8)
    assert plus["polarization_x"] == pytest.approx(0.0056559705, rel=1e-7)
    assert result["claims"]["transmission_even_in_tau"]["passes"] is True
    assert result["claims"]["polarization_x_odd_in_tau"]["passes"] is True
    assert all(
        all(diagnostic.values()) for diagnostic in result["diagnostics"].values()
    )
