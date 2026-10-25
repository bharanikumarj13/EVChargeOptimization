import pytest
from app.optimization.heuristics import (
    calculate_partner_heuristic_operational_demand,
    validate_energy_power_vehicle_semantics,
)


def test_calculate_partner_heuristic_operational_demand():
    # Case 1: baseline exceeds allocated energy
    # max(300.0, 250.0) -> 300.0
    res1 = calculate_partner_heuristic_operational_demand(baseline_energy_kwh=300.0, allocated_energy_kwh=250.0)
    assert res1 == 300.0

    # Case 2: allocated energy exceeds baseline
    # max(200.0, 320.5) -> 320.5
    res2 = calculate_partner_heuristic_operational_demand(baseline_energy_kwh=200.0, allocated_energy_kwh=320.5)
    assert res2 == 320.5

    # Case 3: identical values
    res3 = calculate_partner_heuristic_operational_demand(baseline_energy_kwh=150.0, allocated_energy_kwh=150.0)
    assert res3 == 150.0

    # Negative energy rejected
    with pytest.raises(ValueError):
        calculate_partner_heuristic_operational_demand(baseline_energy_kwh=-10.0, allocated_energy_kwh=100.0)


def test_validate_energy_power_vehicle_semantics():
    sem = validate_energy_power_vehicle_semantics(
        predicted_arrivals=14.0,
        predicted_energy_kwh=280.0,
        allocated_power_kw=350.0,
        allocated_energy_kwh=275.0,
    )
    assert sem["arrival_sessions_count"] == 14.0
    assert sem["baseline_energy_demand_kwh"] == 280.0
    assert sem["active_power_allocation_kw"] == 350.0
    assert sem["served_energy_delivered_kwh"] == 275.0
    assert sem["units"]["arrivals"] == "vehicle_sessions"
    assert sem["units"]["predicted_energy"] == "kWh"
    assert sem["units"]["allocated_power"] == "kW"
    assert sem["units"]["allocated_energy"] == "kWh"

    # Negative arrivals rejected
    with pytest.raises(ValueError):
        validate_energy_power_vehicle_semantics(-1.0, 100.0, 50.0, 50.0)
