"""
Verification script: Demonstrates and tests the complete feedback loop cycle programmatically.
1. Baseline forecast retrieval
2. Constraint-aware allocation execution
3. Impact simulation
4. Feedback generation & submission to mock predictor adapter
5. Next-interval operational demand adjustment calculation
6. Subsequent allocation execution using feedback-adjusted operational demand
7. Invariance verification: Baseline remains unchanged, no double counting, idempotency protection.
"""
import sys
import os
from datetime import datetime, timezone

# Add backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.services.allocation_service import AllocationService
from app.services.feedback_service import FeedbackService
from app.repositories.forecast_snapshot_repo import ForecastSnapshotRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.schemas.allocation import AllocationRunRequest
from app.schemas.feedback import FeedbackCreateRequest
from app.integrations import get_forecast_provider


def run_demo():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("⚡ EVCHARGE-OPT: FEEDBACK LOOP DEMONSTRATION & VERIFICATION")
        print("=" * 70)

        allocation_service = AllocationService(db)
        feedback_service = FeedbackService(db)
        snapshot_repo = ForecastSnapshotRepository(db)
        provider = get_forecast_provider()

        scenario_id = "SCN-001"
        forecast_id = "FC-001"
        int1_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        int1_end = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)

        # -------------------------------------------------------------
        # Step 1: Retrieve and verify baseline forecast
        # -------------------------------------------------------------
        print("\n[STEP 1] Fetching baseline forecast...")
        forecast = provider.get_forecast(forecast_id, scenario_id)
        stn1_baseline_int1 = next(
            item for item in forecast.intervals
            if item.station_id == "STN-01" and item.interval_start == int1_start
        )
        print(f"  • Forecast ID: {forecast.forecast_id}")
        print(f"  • Total intervals: {len(forecast.intervals)}")
        print(f"  • Baseline STN-01 (08:00): {stn1_baseline_int1.predicted_arrivals} veh, {stn1_baseline_int1.predicted_energy_kwh} kWh")

        # -------------------------------------------------------------
        # Step 2: Run Allocation for Interval 1
        # -------------------------------------------------------------
        print("\n[STEP 2] Running allocation for Interval 1 (08:00 - 09:00)...")
        req1 = AllocationRunRequest(
            scenario_id=scenario_id,
            forecast_id=forecast_id,
            interval_start=int1_start,
            interval_end=int1_end,
            operational_adjustment_id=None,
        )
        run1 = allocation_service.run_allocation(req1)
        print(f"  • Allocation 1 ID: {run1.allocation_id}")
        print(f"  • Status: {run1.status}")
        print(f"  • Constraints Validated: {run1.constraint_validation_passed}")
        for r in run1.results:
            print(f"    - Station {r.station_id}: Demand {r.predicted_arrivals} veh -> Served: {r.estimated_served}, Unserved: {r.estimated_unserved}, Power: {r.allocated_power_kw} kW, Wait: {r.estimated_wait_minutes}m, Util: {r.charger_utilization_pct}%")

        # -------------------------------------------------------------
        # Step 3: Generate and Submit Feedback
        # -------------------------------------------------------------
        print("\n[STEP 3] Generating & submitting feedback for Allocation 1...")
        feedback_req = FeedbackCreateRequest(
            deferred_fraction=0.70,
            idempotency_key=f"DEMO-IDEMP-{run1.allocation_id}",
        )
        feedback_resp = feedback_service.submit_allocation_feedback(run1.allocation_id, feedback_req)
        print(f"  • Feedback ID: {feedback_resp.feedback_id}")
        print(f"  • Submission Status: {feedback_resp.submission_status}")
        print(f"  • Deferred Fraction: {feedback_resp.deferred_fraction * 100}%")
        print(f"  • Generated Operational Adjustment ID: {feedback_resp.operational_adjustment_id}")

        for o in feedback_resp.station_outcomes:
            print(f"    - {o.station_id}: Unserved {o.estimated_unserved} veh -> Deferred to next interval: {o.deferred_vehicles} veh ({o.deferred_energy_kwh} kWh)")

        # -------------------------------------------------------------
        # Step 4: Run Subsequent Allocation (Interval 2) with Adjusted Operational Demand
        # -------------------------------------------------------------
        int2_start = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
        int2_end = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)

        print("\n[STEP 4] Executing subsequent allocation for Interval 2 (09:00 - 10:00) using Operational Adjustment...")
        req2 = AllocationRunRequest(
            scenario_id=scenario_id,
            forecast_id=forecast_id,
            interval_start=int2_start,
            interval_end=int2_end,
            operational_adjustment_id=feedback_resp.operational_adjustment_id,
        )
        run2 = allocation_service.run_allocation(req2)
        print(f"  • Allocation 2 ID: {run2.allocation_id}")
        print(f"  • Linked Operational Adjustment: {run2.operational_adjustment_id}")
        print(f"  • Status: {run2.status}")
        for r in run2.results:
            print(f"    - Station {r.station_id}: Feedback-Adjusted Demand: {r.predicted_arrivals} veh, Served: {r.estimated_served}, Unserved: {r.estimated_unserved}, Power: {r.allocated_power_kw} kW")

        # -------------------------------------------------------------
        # Step 5: Verification of Immutability, Deduplication & Idempotency
        # -------------------------------------------------------------
        print("\n[STEP 5] Verification Checks:")

        # 5a. Baseline immutability
        fresh_forecast = provider.get_forecast(forecast_id, scenario_id)
        stn1_fresh_int1 = next(
            item for item in fresh_forecast.intervals
            if item.station_id == "STN-01" and item.interval_start == int1_start
        )
        assert stn1_fresh_int1.predicted_arrivals == stn1_baseline_int1.predicted_arrivals, "Baseline arrivals modified!"
        assert stn1_fresh_int1.predicted_energy_kwh == stn1_baseline_int1.predicted_energy_kwh, "Baseline energy modified!"
        print("  ✅ 1. Baseline forecast snapshot remained strictly immutable.")

        # 5b. Idempotency test
        print("  • Testing duplicate feedback idempotency...")
        duplicate_feedback = feedback_service.submit_allocation_feedback(run1.allocation_id, feedback_req)
        assert duplicate_feedback.feedback_id == feedback_resp.feedback_id, "Idempotency failed: new feedback created!"
        assert duplicate_feedback.operational_adjustment_id == feedback_resp.operational_adjustment_id
        print("  ✅ 2. Idempotency enforced: duplicate submission cleanly returned existing record.")

        # 5c. Demand conservation
        for r in run1.results:
            assert abs((r.estimated_served + r.estimated_unserved) - r.predicted_arrivals) < 0.01, f"Demand conservation violated for {r.station_id}"
        print("  ✅ 3. Demand conservation holds: served + unserved equals eligible demand for all stations.")

        print("\n🎉 ALL FEEDBACK LOOP INTEGRATION CHECKS PASSED SUCCESSFULLY!\n")

    finally:
        db.close()


if __name__ == "__main__":
    run_demo()
