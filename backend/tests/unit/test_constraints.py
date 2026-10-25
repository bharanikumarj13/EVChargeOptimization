import pytest
from app.models.station import Station
from app.models.grid_group import GridGroup
from app.optimization.constraints import validate_station_config, validate_allocation_constraints


def test_station_config_validation():
    # Valid station
    stn = Station(
        station_id="S1",
        station_name="Test Stn",
        charger_count=5,
        available_chargers=4,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=200.0,
        avg_session_minutes=45.0,
        grid_group_id="G1",
        is_active=True,
    )
    valid, errors = validate_station_config(stn)
    assert valid is True
    assert len(errors) == 0

    # Invalid: available > installed
    stn_invalid = Station(
        station_id="S2",
        station_name="Invalid Stn",
        charger_count=4,
        available_chargers=5,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=200.0,
        avg_session_minutes=45.0,
        grid_group_id="G1",
        is_active=True,
    )
    valid, errors = validate_station_config(stn_invalid)
    assert valid is False
    assert any("exceeds installed" in e for e in errors)


def test_allocation_constraints_residual_grid():
    group = GridGroup(
        grid_group_id="G1",
        grid_group_name="Main Grid",
        grid_limit_kw=300.0,
        other_load_kw=100.0,  # residual is 200.0 kW
    )
    stn1 = Station(
        station_id="S1",
        station_name="Stn 1",
        charger_count=4,
        available_chargers=4,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=200.0,
        avg_session_minutes=30.0,
        grid_group_id="G1",
        is_active=True,
    )
    stn2 = Station(
        station_id="S2",
        station_name="Stn 2",
        charger_count=4,
        available_chargers=4,
        charger_power_kw_per_charger=50.0,
        station_power_limit_kw=200.0,
        avg_session_minutes=30.0,
        grid_group_id="G1",
        is_active=True,
    )

    # Allocating 120 kW to S1 and 70 kW to S2 = 190 kW <= 200 kW residual -> passes
    allocations = {
        "S1": {"allocated_power_kw": 120.0},
        "S2": {"allocated_power_kw": 70.0},
    }
    result = validate_allocation_constraints([stn1, stn2], {"G1": group}, allocations)
    assert result.passed is True
    assert len(result.violations) == 0

    # Allocating 150 kW + 100 kW = 250 kW > 200 kW residual -> fails
    allocations_overflow = {
        "S1": {"allocated_power_kw": 150.0},
        "S2": {"allocated_power_kw": 100.0},
    }
    result_overflow = validate_allocation_constraints([stn1, stn2], {"G1": group}, allocations_overflow)
    assert result_overflow.passed is False
    assert any("exceeds residual grid capacity" in v for v in result_overflow.violations)
