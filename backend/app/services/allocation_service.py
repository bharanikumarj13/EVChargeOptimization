import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.models.scenario import Scenario
from app.models.station import Station
from app.models.grid_group import GridGroup
from app.models.operational_adjustment import OperationalAdjustment
from app.repositories.station_repo import StationRepository
from app.repositories.grid_group_repo import GridGroupRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.repositories.allocation_repo import AllocationRepository
from app.repositories.forecast_snapshot_repo import ForecastSnapshotRepository
from app.repositories.audit_repo import AuditRepository
from app.integrations import get_forecast_provider
from app.integrations.station_mapper import StationMapper
from app.optimization.engine import AllocationEngine
from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, InvalidForecastError, StationMappingError
from app.schemas.allocation import AllocationRunRequest, AllocationRunResponse, StationAllocationResultSchema


class AllocationService:
    def __init__(self, db: Session):
        self.db = db
        self.station_repo = StationRepository(db)
        self.grid_group_repo = GridGroupRepository(db)
        self.scenario_repo = ScenarioRepository(db)
        self.allocation_repo = AllocationRepository(db)
        self.snapshot_repo = ForecastSnapshotRepository(db)
        self.audit_repo = AuditRepository(db)

    def run_allocation(self, req: AllocationRunRequest) -> AllocationRunResponse:
        # 1. Validate scenario
        scenario = self.scenario_repo.get_by_id(req.scenario_id)
        if not scenario:
            raise EntityNotFoundError("Scenario", req.scenario_id)

        # 2. Retrieve stations and grid groups
        stations = self.station_repo.get_all()
        if not stations:
            raise InvalidForecastError("No charging stations configured. Please add stations before optimizing.")

        grid_groups = {g.grid_group_id: g for g in self.grid_group_repo.get_all()}

        # 3. Retrieve forecast
        provider = get_forecast_provider()
        forecast = provider.get_forecast(req.forecast_id, req.scenario_id)

        # Ensure forecast snapshot is persisted if not already present
        existing_snapshots = self.snapshot_repo.get_by_forecast_id(req.forecast_id)
        if not existing_snapshots and forecast.intervals:
            self.snapshot_repo.save_snapshot(
                snapshot_id=f"SNAP-{uuid.uuid4().hex[:8].upper()}",
                items=forecast.intervals,
            )

        # 4. Determine demand for the requested interval
        # Check if an operational adjustment was supplied (feedback-adjusted demand)
        demand_by_station: Dict[str, Dict[str, float]] = {}
        target_interval_start_iso = req.interval_start.isoformat()
        known_station_ids = {s.station_id for s in stations}

        # Enforce physical verification safeguard in live mode
        is_live_mode = (scenario.provider_mode == "live" or not settings.is_mock_provider)
        require_physical_confirmed = is_live_mode and not getattr(settings, "CONFIRM_PHYSICAL_STATION_MAPPINGS", False)

        if req.operational_adjustment_id:
            adj = (
                self.db.query(OperationalAdjustment)
                .filter(OperationalAdjustment.operational_adjustment_id == req.operational_adjustment_id)
                .first()
            )
            if not adj:
                raise EntityNotFoundError("OperationalAdjustment", req.operational_adjustment_id)

            # Use feedback-adjusted operational demand numbers
            adj_data = json.loads(adj.station_adjustments_json)
            for item in adj_data:
                internal_stn_id = StationMapper.to_internal(
                    item["station_id"],
                    known_internal_ids=known_station_ids,
                    require_physical_confirmed=require_physical_confirmed,
                )
                demand_by_station[internal_stn_id] = {
                    "predicted_arrivals": item["adjusted_predicted_arrivals"],
                    "predicted_energy_kwh": item["adjusted_predicted_energy_kwh"],
                }
        else:
            # Match baseline forecast intervals with robust timezone handling
            req_start = req.interval_start if req.interval_start.tzinfo is not None else req.interval_start.replace(tzinfo=timezone.utc)
            matching_items = []
            for item in forecast.intervals:
                item_start = item.interval_start if item.interval_start.tzinfo is not None else item.interval_start.replace(tzinfo=timezone.utc)
                if abs((item_start - req_start).total_seconds()) < 60:
                    matching_items.append(item)

            if not matching_items:
                raise InvalidForecastError(
                    f"Requested interval start '{req.interval_start.isoformat()}' is outside the forecast horizon "
                    f"for forecast '{req.forecast_id}'. Timestamps must match a valid forecast interval."
                )

            for item in matching_items:
                internal_stn_id = StationMapper.to_internal(
                    item.station_id,
                    known_internal_ids=known_station_ids,
                    require_physical_confirmed=require_physical_confirmed,
                )
                demand_by_station[internal_stn_id] = {
                    "predicted_arrivals": item.predicted_arrivals,
                    "predicted_energy_kwh": item.predicted_energy_kwh,
                }

        # Filter station scope based on the active station integration profile
        profile_station_ids = set(StationMapper.get_profile_stations())
        scoped_stations = [s for s in stations if s.station_id in profile_station_ids]

        # Validate that all active stations within the profile scope have forecast demand
        missing_active = [
            stn.station_id for stn in scoped_stations
            if stn.is_active and stn.station_id not in demand_by_station
        ]
        if missing_active:
            raise InvalidForecastError(
                f"Active station(s) {missing_active} have no forecast demand for interval '{req.interval_start.isoformat()}'. "
                f"Forecast must provide demand for all active stations in the active profile.",
                validation_errors=[{"missing_stations": missing_active}],
            )

        # Inactive stations get zero demand
        for stn in scoped_stations:
            if not stn.is_active and stn.station_id not in demand_by_station:
                demand_by_station[stn.station_id] = {"predicted_arrivals": 0.0, "predicted_energy_kwh": 0.0}

        # 5. Run deterministic optimization engine on scoped stations
        interval_minutes = int((req.interval_end - req.interval_start).total_seconds() / 60.0)
        if interval_minutes <= 0:
            interval_minutes = 60

        passed, status, station_results, warnings = AllocationEngine.optimize(
            stations=scoped_stations,
            grid_groups=grid_groups,
            demand_by_station=demand_by_station,
            interval_minutes=interval_minutes,
        )

        # 6. Persist allocation run and child results
        allocation_id = f"ALC-{uuid.uuid4().hex[:8].upper()}"
        run_data = {
            "allocation_id": allocation_id,
            "scenario_id": req.scenario_id,
            "forecast_id": req.forecast_id,
            "operational_adjustment_id": req.operational_adjustment_id,
            "interval_start": req.interval_start,
            "interval_end": req.interval_end,
            "status": status,
            "outcome_kind": "simulation",
            "algorithm_version": AllocationEngine.ALGORITHM_VERSION,
            "objective_description": AllocationEngine.OBJECTIVE_DESCRIPTION,
            "constraint_validation_passed": passed,
            "warnings_json": json.dumps(warnings),
        }

        saved_run = self.allocation_repo.create_run_with_results(run_data, station_results)

        # 7. Audit log
        self.audit_repo.log(
            event_type="ALLOCATION_EXECUTED",
            entity_type="AllocationRun",
            entity_id=allocation_id,
            action="EXECUTE",
            details={
                "status": status,
                "passed": passed,
                "stations_count": len(station_results),
                "is_adjusted": req.operational_adjustment_id is not None,
            },
        )

        # 8. Build response
        result_schemas = [
            StationAllocationResultSchema(
                station_id=res["station_id"],
                station_name=res.get("station_name"),
                predicted_arrivals=res["predicted_arrivals"],
                predicted_energy_kwh=res["predicted_energy_kwh"],
                estimated_served=res["estimated_served"],
                estimated_unserved=res["estimated_unserved"],
                allocated_power_kw=res["allocated_power_kw"],
                estimated_served_energy_kwh=res.get("estimated_served_energy_kwh", 0.0),
                estimated_unserved_energy_kwh=res.get("estimated_unserved_energy_kwh", 0.0),
                estimated_wait_minutes=res.get("estimated_wait_minutes"),
                charger_utilization_pct=res.get("charger_utilization_pct", 0.0),
                warnings=res.get("warnings", []),
            )
            for res in station_results
        ]

        return AllocationRunResponse(
            allocation_id=saved_run.allocation_id,
            scenario_id=saved_run.scenario_id,
            forecast_id=saved_run.forecast_id,
            operational_adjustment_id=saved_run.operational_adjustment_id,
            interval_start=saved_run.interval_start,
            interval_end=saved_run.interval_end,
            status=saved_run.status,
            outcome_kind=saved_run.outcome_kind,
            algorithm_version=saved_run.algorithm_version,
            objective_description=saved_run.objective_description,
            constraint_validation_passed=saved_run.constraint_validation_passed,
            warnings=warnings,
            results=result_schemas,
            created_at=saved_run.created_at,
        )
