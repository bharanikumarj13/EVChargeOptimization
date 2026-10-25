import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.feedback import FeedbackRecord
from app.models.operational_adjustment import OperationalAdjustment
from app.repositories.allocation_repo import AllocationRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.operational_adjustment_repo import OperationalAdjustmentRepository
from app.repositories.audit_repo import AuditRepository
from app.integrations import get_forecast_provider
from app.core.exceptions import EntityNotFoundError, ProviderIntegrationError
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse, StationFeedbackOutcome


class FeedbackService:
    def __init__(self, db: Session):
        self.db = db
        self.allocation_repo = AllocationRepository(db)
        self.feedback_repo = FeedbackRepository(db)
        self.adjustment_repo = OperationalAdjustmentRepository(db)
        self.audit_repo = AuditRepository(db)

    def submit_allocation_feedback(
        self,
        allocation_id: str,
        req: Optional[FeedbackCreateRequest] = None,
    ) -> FeedbackResponse:
        allocation = self.allocation_repo.get_by_id(allocation_id)
        if not allocation:
            raise EntityNotFoundError("AllocationRun", allocation_id)

        deferred_fraction = req.deferred_fraction if req and req.deferred_fraction is not None else 0.70
        idempotency_key = (
            req.idempotency_key
            if (req and req.idempotency_key)
            else f"IDEMP-{allocation_id}-{deferred_fraction}"
        )

        # 1. Enforce Idempotency: Return existing record if already processed
        existing = self.feedback_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            adj = self.adjustment_repo.get_by_source_feedback(existing.feedback_id)
            return self._build_response(existing, adj.operational_adjustment_id if adj else None)

        # 2. Extract station outcomes from persisted allocation results
        outcomes: List[StationFeedbackOutcome] = []
        for res in allocation.results:
            def_veh = round(res.estimated_unserved * deferred_fraction, 1)
            def_kwh = round(res.estimated_unserved_energy_kwh * deferred_fraction, 1)
            outcomes.append(
                StationFeedbackOutcome(
                    station_id=res.station_id,
                    predicted_arrivals=res.predicted_arrivals,
                    estimated_served=res.estimated_served,
                    estimated_unserved=res.estimated_unserved,
                    allocated_power_kw=res.allocated_power_kw,
                    estimated_wait_minutes=res.estimated_wait_minutes,
                    charger_utilization_pct=res.charger_utilization_pct,
                    deferred_vehicles=def_veh,
                    deferred_energy_kwh=def_kwh,
                )
            )

        feedback_id = f"FBD-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "feedback_id": feedback_id,
            "scenario_id": allocation.scenario_id,
            "forecast_id": allocation.forecast_id,
            "allocation_id": allocation.allocation_id,
            "outcome_kind": allocation.outcome_kind,
            "interval_start": allocation.interval_start.isoformat(),
            "interval_end": allocation.interval_end.isoformat(),
            "deferred_fraction": deferred_fraction,
            "station_outcomes": [o.model_dump() for o in outcomes],
        }

        # 3. Submit feedback to provider adapter
        provider = get_forecast_provider()
        submission_status = "submitted"
        error_details = None

        try:
            provider.submit_feedback(payload)
        except ProviderIntegrationError as pie:
            submission_status = "failed"
            error_details = pie.message
        except Exception as exc:
            submission_status = "failed"
            error_details = str(exc)

        # 4. Persist feedback record
        record_data = {
            "feedback_id": feedback_id,
            "scenario_id": allocation.scenario_id,
            "forecast_id": allocation.forecast_id,
            "allocation_id": allocation.allocation_id,
            "outcome_kind": allocation.outcome_kind,
            "interval_start": allocation.interval_start,
            "interval_end": allocation.interval_end,
            "station_outcomes_json": json.dumps([o.model_dump() for o in outcomes]),
            "deferred_fraction": deferred_fraction,
            "submission_status": submission_status,
            "idempotency_key": idempotency_key,
            "retry_count": 0,
            "error_details": error_details,
        }

        feedback_obj = self.feedback_repo.create(record_data)

        # 5. If successfully submitted, calculate / retrieve operational demand adjustment for next interval
        adjustment_id: Optional[str] = None
        if submission_status == "submitted":
            interval_duration = allocation.interval_end - allocation.interval_start
            target_start = allocation.interval_end
            target_end = target_start + interval_duration

            adj_response = provider.get_next_operational_adjustment(
                feedback_id=feedback_id,
                target_interval_start=target_start.isoformat(),
                target_interval_end=target_end.isoformat(),
            )

            if adj_response:
                adjustment_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
                adj_data = {
                    "operational_adjustment_id": adjustment_id,
                    "source_feedback_id": feedback_id,
                    "parent_forecast_id": allocation.forecast_id,
                    "target_interval_start": target_start,
                    "target_interval_end": target_end,
                    "station_adjustments_json": json.dumps(adj_response.get("station_adjustments", [])),
                    "deferred_demand_contribution_json": json.dumps([
                        {
                            "station_id": o.station_id,
                            "deferred_vehicles": o.deferred_vehicles,
                            "deferred_energy_kwh": o.deferred_energy_kwh,
                        }
                        for o in outcomes
                    ]),
                    "calculation_assumptions_json": json.dumps(adj_response.get("calculation_assumptions", {})),
                }
                self.adjustment_repo.create(adj_data)

        # 6. Audit log
        self.audit_repo.log(
            event_type="FEEDBACK_SUBMITTED",
            entity_type="FeedbackRecord",
            entity_id=feedback_id,
            action="SUBMIT",
            details={
                "status": submission_status,
                "allocation_id": allocation_id,
                "adjustment_id": adjustment_id,
            },
        )

        return self._build_response(feedback_obj, adjustment_id)

    def _build_response(self, record: FeedbackRecord, operational_adjustment_id: Optional[str]) -> FeedbackResponse:
        outcomes_raw = json.loads(record.station_outcomes_json)
        station_outcomes = [StationFeedbackOutcome(**o) for o in outcomes_raw]

        return FeedbackResponse(
            feedback_id=record.feedback_id,
            scenario_id=record.scenario_id,
            forecast_id=record.forecast_id,
            allocation_id=record.allocation_id,
            outcome_kind=record.outcome_kind,
            interval_start=record.interval_start,
            interval_end=record.interval_end,
            station_outcomes=station_outcomes,
            deferred_fraction=record.deferred_fraction,
            submission_status=record.submission_status,
            idempotency_key=record.idempotency_key,
            retry_count=record.retry_count,
            error_details=record.error_details,
            operational_adjustment_id=operational_adjustment_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
