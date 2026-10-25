import io
import csv
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.station import Station
from app.models.grid_group import GridGroup
from app.models.scenario import Scenario
from app.models.allocation import AllocationRun, AllocationResult
from app.models.feedback import FeedbackRecord
from app.core.security import sanitize_csv_cell


class ReportingService:
    def __init__(self, db: Session):
        self.db = db

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Calculates system-wide operational metrics from persisted data."""
        stations = self.db.query(Station).all()
        grid_groups = self.db.query(GridGroup).all()

        total_stations = len(stations)
        active_stations = sum(1 for s in stations if s.is_active)
        total_installed_chargers = sum(s.charger_count for s in stations)
        total_available_chargers = sum(s.available_chargers for s in stations if s.is_active)

        total_grid_limit_kw = sum(g.grid_limit_kw for g in grid_groups)
        total_residual_grid_kw = sum(g.residual_capacity_kw for g in grid_groups)

        allocations = self.db.query(AllocationRun).order_by(AllocationRun.created_at.desc()).all()
        total_runs = len(allocations)
        latest_run = allocations[0] if allocations else None

        # Aggregate across all results
        aggregates = self.db.query(
            func.sum(AllocationResult.predicted_arrivals).label("total_arrivals"),
            func.sum(AllocationResult.estimated_served).label("total_served"),
            func.sum(AllocationResult.estimated_unserved).label("total_unserved"),
            func.sum(AllocationResult.allocated_power_kw).label("total_power_kw"),
            func.avg(AllocationResult.charger_utilization_pct).label("avg_utilization"),
        ).first()

        recent_feedbacks = (
            self.db.query(FeedbackRecord)
            .order_by(FeedbackRecord.created_at.desc())
            .limit(5)
            .all()
        )

        return {
            "total_stations": total_stations,
            "active_stations": active_stations,
            "total_installed_chargers": total_installed_chargers,
            "total_available_chargers": total_available_chargers,
            "total_grid_limit_kw": round(total_grid_limit_kw, 1),
            "total_residual_grid_kw": round(total_residual_grid_kw, 1),
            "total_optimization_runs": total_runs,
            "total_predicted_arrivals": round(aggregates.total_arrivals or 0.0, 1),
            "total_estimated_served": round(aggregates.total_served or 0.0, 1),
            "total_estimated_unserved": round(aggregates.total_unserved or 0.0, 1),
            "total_allocated_power_kw": round(aggregates.total_power_kw or 0.0, 1),
            "avg_charger_utilization_pct": round(aggregates.avg_utilization or 0.0, 1),
            "latest_allocation_id": latest_run.allocation_id if latest_run else None,
            "latest_run_status": latest_run.status if latest_run else None,
            "recent_feedback_count": len(recent_feedbacks),
        }

    def generate_allocations_csv(self) -> str:
        """
        Generates CSV export of all station-level allocation results with
        strict formula-injection protection (RFC 4180 + CWE-1236 mitigation).
        """
        results = (
            self.db.query(AllocationResult, AllocationRun)
            .join(AllocationRun, AllocationResult.allocation_id == AllocationRun.allocation_id)
            .order_by(AllocationRun.created_at.desc(), AllocationResult.station_id)
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        headers = [
            "Allocation ID",
            "Scenario ID",
            "Forecast ID",
            "Operational Adjustment ID",
            "Interval Start",
            "Interval End",
            "Status",
            "Outcome Kind",
            "Station ID",
            "Predicted Arrivals",
            "Predicted Energy (kWh)",
            "Estimated Served",
            "Estimated Unserved",
            "Allocated Power (kW)",
            "Estimated Served Energy (kWh)",
            "Estimated Unserved Energy (kWh)",
            "Estimated Wait (min)",
            "Charger Utilization (%)",
            "Constraint Validation Passed",
            "Created At",
        ]
        writer.writerow(headers)

        for res, run in results:
            row = [
                sanitize_csv_cell(run.allocation_id),
                sanitize_csv_cell(run.scenario_id),
                sanitize_csv_cell(run.forecast_id),
                sanitize_csv_cell(run.operational_adjustment_id or "N/A"),
                sanitize_csv_cell(run.interval_start.isoformat()),
                sanitize_csv_cell(run.interval_end.isoformat()),
                sanitize_csv_cell(run.status),
                sanitize_csv_cell(run.outcome_kind),
                sanitize_csv_cell(res.station_id),
                sanitize_csv_cell(res.predicted_arrivals),
                sanitize_csv_cell(res.predicted_energy_kwh),
                sanitize_csv_cell(res.estimated_served),
                sanitize_csv_cell(res.estimated_unserved),
                sanitize_csv_cell(res.allocated_power_kw),
                sanitize_csv_cell(res.estimated_served_energy_kwh),
                sanitize_csv_cell(res.estimated_unserved_energy_kwh),
                sanitize_csv_cell(res.estimated_wait_minutes if res.estimated_wait_minutes is not None else "N/A"),
                sanitize_csv_cell(res.charger_utilization_pct),
                sanitize_csv_cell(run.constraint_validation_passed),
                sanitize_csv_cell(run.created_at.isoformat()),
            ]
            writer.writerow(row)

        return output.getvalue()
