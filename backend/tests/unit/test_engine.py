import pytest
from app.models.station import Station
from app.models.grid_group import GridGroup
from app.optimization.engine import AllocationEngine


def test_allocation_engine_deterministic_results():
    gg = GridGroup(
        grid_group_id="GRID-METRO",
        grid_group_name="Metro Substation",
        grid_limit_kw=500.0,
        other_load_kw=100.0,  # 400 kW residual
    )
    stn1 = Station(
        station_id="STN-01",
        station_name="Station 1",
        charger_count=6,
        available_chargers=6,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=250.0,
        avg_session_minutes=40.0,
        grid_group_id="GRID-METRO",
        is_active=True,
    )

    demand = {
        "STN-01": {"predicted_arrivals": 12.0, "predicted_energy_kwh": 240.0}
    }

    # Run twice with identical input
    p1, s1, r1, w1 = AllocationEngine.optimize([stn1], {"GRID-METRO": gg}, demand, 60)
    p2, s2, r2, w2 = AllocationEngine.optimize([stn1], {"GRID-METRO": gg}, demand, 60)

    assert p1 is True
    assert s1 == "success"
    assert r1[0]["estimated_served"] == r2[0]["estimated_served"]
    assert r1[0]["allocated_power_kw"] == r2[0]["allocated_power_kw"]
    assert r1[0]["estimated_served"] + r1[0]["estimated_unserved"] == 12.0


def test_allocation_inactive_station_gets_zero_power():
    gg = GridGroup(grid_group_id="G1", grid_group_name="G1", grid_limit_kw=500.0, other_load_kw=0.0)
    stn = Station(
        station_id="STN-OFF",
        station_name="Deactivated Station",
        charger_count=4,
        available_chargers=4,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=200.0,
        avg_session_minutes=45.0,
        grid_group_id="G1",
        is_active=False,
    )
    demand = {"STN-OFF": {"predicted_arrivals": 10.0, "predicted_energy_kwh": 200.0}}

    passed, status, results, warnings = AllocationEngine.optimize([stn], {"G1": gg}, demand, 60)
    assert passed is True
    assert results[0]["allocated_power_kw"] == 0.0
    assert results[0]["estimated_served"] == 0.0
    assert results[0]["estimated_unserved"] == 10.0
