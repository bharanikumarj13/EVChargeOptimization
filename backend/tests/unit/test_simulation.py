import pytest
from app.simulation.impact import calculate_waiting_time, calculate_utilization, calculate_deferred_demand


def test_calculate_waiting_time():
    # Zero arrivals
    assert calculate_waiting_time(0.0, 10.0, 45.0) == 0.0
    assert calculate_waiting_time(0.0, 0.0, 45.0) == 0.0

    # Zero available capacity with positive arrivals returns None (unavailable)
    assert calculate_waiting_time(5.0, 0.0, 45.0) is None
    assert calculate_waiting_time(10.0, -1.0, 45.0) is None

    # Low load (within turnover capacity)
    wait_low = calculate_waiting_time(5.0, 10.0, 40.0)
    assert wait_low is not None
    assert 0.0 < wait_low < 40.0

    # Saturated queue (arrivals > turnover capacity)
    wait_high = calculate_waiting_time(15.0, 10.0, 40.0)
    assert wait_high is not None
    assert wait_high > wait_low


def test_calculate_utilization():
    # 5 served * 30 mins = 150 occupied mins. 4 chargers * 60 mins = 240 avail mins.
    # 150 / 240 = 62.5%
    util = calculate_utilization(estimated_served=5.0, avg_session_minutes=30.0, available_chargers=4, interval_minutes=60)
    assert util == 62.5

    # Safe zero chargers
    assert calculate_utilization(5.0, 30.0, 0, 60) == 0.0


def test_calculate_deferred_demand():
    res = calculate_deferred_demand(unserved_vehicles=10.0, unserved_energy_kwh=250.0, deferred_fraction=0.70)
    assert res["deferred_vehicles"] == 7.0
    assert res["deferred_energy_kwh"] == 175.0
    assert res["deferred_fraction"] == 0.70
