import json
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.allocation import AllocationRun, AllocationResult


class AllocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, allocation_id: str) -> Optional[AllocationRun]:
        return self.db.query(AllocationRun).filter(AllocationRun.allocation_id == allocation_id).first()

    def get_by_scenario(self, scenario_id: str, limit: int = 100) -> List[AllocationRun]:
        return (
            self.db.query(AllocationRun)
            .filter(AllocationRun.scenario_id == scenario_id)
            .order_by(AllocationRun.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(self, limit: int = 50) -> List[AllocationRun]:
        return (
            self.db.query(AllocationRun)
            .order_by(AllocationRun.created_at.desc())
            .limit(limit)
            .all()
        )

    def create_run_with_results(
        self,
        run_data: dict,
        station_results: List[dict],
    ) -> AllocationRun:
        run = AllocationRun(**run_data)
        self.db.add(run)
        self.db.flush()  # Ensure allocation_id is active for child results

        for res in station_results:
            result_obj = AllocationResult(
                allocation_id=run.allocation_id,
                station_id=res["station_id"],
                predicted_arrivals=res["predicted_arrivals"],
                predicted_energy_kwh=res["predicted_energy_kwh"],
                estimated_served=res["estimated_served"],
                estimated_unserved=res["estimated_unserved"],
                allocated_power_kw=res["allocated_power_kw"],
                estimated_served_energy_kwh=res.get("estimated_served_energy_kwh", 0.0),
                estimated_unserved_energy_kwh=res.get("estimated_unserved_energy_kwh", 0.0),
                estimated_wait_minutes=res.get("estimated_wait_minutes"),
                charger_utilization_pct=res.get("charger_utilization_pct", 0.0),
                warnings_json=json.dumps(res.get("warnings", [])),
            )
            self.db.add(result_obj)

        self.db.commit()
        self.db.refresh(run)
        return run
