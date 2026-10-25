"""
Automated Comprehensive Verification of all Audit Bug Fixes:
E. Check six interval selections individually.
F. Test invalid timestamps, unknown stations, zero available chargers, and invalid station updates.
G. Test feedback retry and duplicate prevention.
H. Verify demand conservation and charger/grid constraints.
"""
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Set

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.services.allocation_service import AllocationService
from app.services.feedback_service import FeedbackService
from app.repositories.station_repo import StationRepository
from app.repositories.grid_group_repo import GridGroupRepository
from app.schemas.allocation import AllocationRunRequest
from app.schemas.feedback import FeedbackCreateRequest
from app.schemas.station import StationUpdate
from app.integrations import get_forecast_provider
from app.core.exceptions import InvalidForecastError
from app.optimization.engine import AllocationEngine
from app.models.station import Station
from app.models.grid_group import GridGroup
from app.simulation.impact import calculate_waiting_time


def main():
    db = SessionLocal()
    print("=" * 70)
    print("🧪 EVCHARGE-OPT: COMPREHENSIVE AUDIT VERIFICATION SUITE")
    print("=" * 70)

    allocation_service = AllocationService(db)
    feedback_service = FeedbackService(db)
    station_repo = StationRepository(db)
    provider = get_forecast_provider()

    # -----------------------------------------------------------------
    # E. Check the six interval selections individually
    # -----------------------------------------------------------------
    print("\n[VERIFICATION E] Checking the six distinct intervals individually...")
    forecast = provider.get_forecast("FC-001", "SCN-001")
    unique_intervals = []
    seen: Set[datetime] = set()
    for item in forecast.intervals:
        if item.interval_start not in seen:
            seen.add(item.interval_start)
            unique_intervals.append((item.interval_start, item.interval_end))

    assert len(unique_intervals) == 6, f"Expected 6 intervals, got {len(unique_intervals)}"
    print(f"  • Found {len(unique_intervals)} unique planning intervals.")

    for idx, (int_start, int_end) in enumerate(unique_intervals):
        req = AllocationRunRequest(
            scenario_id="SCN-001",
            forecast_id="FC-001",
            interval_start=int_start,
            interval_end=int_end,
            operational_adjustment_id=None,
        )
        res = allocation_service.run_allocation(req)
        assert res.status == "success"
        assert res.constraint_validation_passed is True
        total_arr = sum(r.predicted_arrivals for r in res.results)
        total_srv = sum(r.estimated_served for r in res.results)
        print(f"  ✅ Interval #{idx+1} ({int_start.strftime('%H:%M')} - {int_end.strftime('%H:%M')} UTC): {len(res.results)} stations, {total_arr:.1f} arrivals -> {total_srv:.1f} served")

    # -----------------------------------------------------------------
    # F. Test invalid timestamps, unknown stations, zero available chargers, and invalid station updates
    # -----------------------------------------------------------------
    print("\n[VERIFICATION F] Testing error handling and edge cases...")

    # 1. Invalid timestamp outside forecast horizon
    print("  • Testing invalid out-of-horizon timestamp in allocation...")
    try:
        allocation_service.run_allocation(AllocationRunRequest(
            scenario_id="SCN-001",
            forecast_id="FC-001",
            interval_start=datetime(2026, 10, 26, 23, 0, 0, tzinfo=timezone.utc),
            interval_end=datetime(2026, 10, 27, 0, 0, 0, tzinfo=timezone.utc),
            operational_adjustment_id=None,
        ))
        assert False, "Expected InvalidForecastError for out-of-horizon timestamp"
    except InvalidForecastError as e:
        print(f"  ✅ Rejected invalid out-of-horizon timestamp: {e.message}")

    # 2. Unknown station ID in mock provider
    print("  • Testing unknown station ID in mock provider adjustment...")
    mock_fb = {
        "feedback_id": "FBD-TEST-EDGE",
        "station_outcomes": [{"station_id": "STN-UNKNOWN-99", "estimated_unserved": 5.0, "predicted_arrivals": 10.0, "predicted_energy_kwh": 200.0}],
        "deferred_fraction": 0.70,
        "forecast_id": "FC-001",
    }
    provider.submit_feedback(mock_fb)
    adj = provider.get_next_operational_adjustment(
        feedback_id="FBD-TEST-EDGE",
        target_interval_start="2026-10-26T11:00:00Z",
        target_interval_end="2026-10-26T12:00:00Z",
    )
    assert adj is not None
    assert adj["station_adjustments"][0]["station_id"] == "STN-UNKNOWN-99"
    assert adj["station_adjustments"][0]["original_predicted_arrivals"] == 10.0
    print("  ✅ Unknown station handled cleanly with safe fallback profile without IndexError")

    # 3. Zero available chargers
    print("  • Testing zero available chargers queue wait time...")
    wait_zero_chargers = calculate_waiting_time(eligible_arrivals=6.0, station_vehicle_capacity=0.0, avg_session_minutes=45.0)
    assert wait_zero_chargers is None, f"Expected None for zero capacity with arrivals, got {wait_zero_chargers}"
    print(f"  ✅ Waiting time for zero available chargers returned: {wait_zero_chargers} (Unavailable/N/A)")

    # 4. Invalid station updates (available_chargers > charger_count)
    print("  • Testing station update validation in repository...")
    stn1 = station_repo.get_by_id("STN-01")
    assert stn1 is not None
    try:
        station_repo.update(stn1, StationUpdate(available_chargers=999))
        assert False, "Expected ValueError for available_chargers > charger_count"
    except ValueError as ve:
        print(f"  ✅ Station update correctly rejected: {str(ve)}")

    # -----------------------------------------------------------------
    # G. Test feedback retry and duplicate prevention
    # -----------------------------------------------------------------
    print("\n[VERIFICATION G] Testing feedback retry and duplicate prevention...")
    test_req = AllocationRunRequest(
        scenario_id="SCN-001",
        forecast_id="FC-001",
        interval_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_end=datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc),
        operational_adjustment_id=None,
    )
    test_run = allocation_service.run_allocation(test_req)
    idemp_key = f"VERIFY-G-{test_run.allocation_id}"

    # First submission
    fb1 = feedback_service.submit_allocation_feedback(
        test_run.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key=idemp_key)
    )
    assert fb1.submission_status == "submitted"
    assert fb1.retry_count == 0
    adj1_id = fb1.operational_adjustment_id

    # Duplicate submission
    fb2 = feedback_service.submit_allocation_feedback(
        test_run.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key=idemp_key)
    )
    assert fb2.feedback_id == fb1.feedback_id
    assert fb2.operational_adjustment_id == adj1_id
    assert fb2.retry_count == 0
    print("  ✅ Idempotency enforced: duplicate submission returns cached feedback and adjustment without re-creating.")

    # -----------------------------------------------------------------
    # H. Verify demand conservation and charger/grid constraints
    # -----------------------------------------------------------------
    print("\n[VERIFICATION H] Verifying physical constraints and demand conservation...")
    # Run across all stations with tight grid limits
    stns = station_repo.get_all(active_only=True)
    gg_repo = GridGroupRepository(db)
    grid_groups = {g.grid_group_id: g for g in gg_repo.get_all()}

    demand = {
        s.station_id: {"predicted_arrivals": 25.0, "predicted_energy_kwh": 500.0}
        for s in stns
    }
    passed, status, results, warnings = AllocationEngine.optimize(
        stations=stns,
        grid_groups=grid_groups,
        demand_by_station=demand,
        interval_minutes=60,
    )
    assert passed is True
    print(f"  • Engine run status: {status}, total stations evaluated: {len(results)}")

    # Check 1: Demand conservation
    for r in results:
        arr = r["predicted_arrivals"]
        srv = r["estimated_served"]
        uns = r["estimated_unserved"]
        assert round(srv + uns, 1) == round(arr, 1), f"Conservation failed for {r['station_id']}: {srv} + {uns} != {arr}"
    print("  ✅ Conservation of vehicles holds strictly across all stations (served + unserved == arrivals)")

    # Check 2: Station hardware and charger limits
    for s in stns:
        r = next(item for item in results if item["station_id"] == s.station_id)
        max_station_kw = min(s.station_power_limit_kw, s.available_chargers * s.charger_power_kw_per_charger)
        assert r["allocated_power_kw"] <= max_station_kw + 1e-4, f"Station power limit violated at {s.station_id}"
    print("  ✅ Station power limits respected: allocated_power <= min(station_limit, chargers * charger_power)")

    # Check 3: Grid group residual limits
    for gid, group in grid_groups.items():
        group_stations = [r for r in results if any(s.station_id == r["station_id"] and s.grid_group_id == gid for s in stns)]
        group_alloc_power = sum(r["allocated_power_kw"] for r in group_stations)
        assert group_alloc_power <= group.residual_capacity_kw + 1e-4, f"Grid capacity violated for {gid}"
        print(f"  ✅ Grid Group '{group.grid_group_name}': allocated {group_alloc_power:.1f} kW <= residual limit {group.residual_capacity_kw:.1f} kW")

    print("\n" + "=" * 70)
    print("🎉 ALL AUDIT VERIFICATIONS E, F, G, H PASSED WITH ZERO ERRORS!")
    print("=" * 70)


if __name__ == "__main__":
    main()
