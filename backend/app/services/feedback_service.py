import uuid
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.feedback import FeedbackRecord
from app.models.operational_adjustment import OperationalAdjustment
from app.repositories.allocation_repo import AllocationRepository
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.operational_adjustment_repo import OperationalAdjustmentRepository
from app.repositories.audit_repo import AuditRepository
from app.integrations import get_forecast_provider
from app.integrations.live_provider import LiveForecastProvider
from app.core.logging import logger
from app.core.exceptions import EntityNotFoundError, ProviderIntegrationError, IdempotencyConflictError
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse, StationFeedbackOutcome


class FeedbackService:
    def __init__(self, db: Session):
        self.db = db
        self.allocation_repo = AllocationRepository(db)
        self.feedback_repo = FeedbackRepository(db)
        self.adjustment_repo = OperationalAdjustmentRepository(db)
        self.audit_repo = AuditRepository(db)

    def resolve_remote_feedback_id(self, local_feedback_id: str) -> Optional[str]:
        """
        Durable remote feedback ID resolution across server restarts.
        Checks:
        1. OperationalAdjustment.calculation_assumptions_json
        2. AuditEvent.details_json for event_type in ('FEEDBACK_SUBMITTED', 'FEEDBACK_RETRIED')
        3. LiveForecastProvider class-level cache
        """
        # 1. Check existing OperationalAdjustment
        adj = self.adjustment_repo.get_by_source_feedback(local_feedback_id)
        if adj and adj.calculation_assumptions_json:
            try:
                assumptions = json.loads(adj.calculation_assumptions_json)
                if assumptions.get("remote_feedback_id"):
                    remote_id = assumptions["remote_feedback_id"]
                    LiveForecastProvider.register_feedback_mapping(local_feedback_id, remote_id)
                    return remote_id
            except Exception:
                pass

        # 2. Check AuditEvent table
        from app.models.audit_event import AuditEvent
        audit_rec = (
            self.db.query(AuditEvent)
            .filter(
                AuditEvent.entity_type == "FeedbackRecord",
                AuditEvent.entity_id == local_feedback_id,
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )
        if audit_rec and audit_rec.details_json:
            try:
                details = json.loads(audit_rec.details_json)
                if details.get("remote_feedback_id"):
                    remote_id = details["remote_feedback_id"]
                    LiveForecastProvider.register_feedback_mapping(local_feedback_id, remote_id)
                    return remote_id
            except Exception:
                pass

        # 3. Fallback to in-memory map
        return LiveForecastProvider._class_local_to_remote_feedback_ids.get(local_feedback_id)

    @staticmethod
    def compute_payload_fingerprint(
        allocation_id: str,
        deferred_fraction: float,
        outcomes: List[StationFeedbackOutcome],
    ) -> str:
        """
        Computes a deterministic SHA-256 fingerprint over normalized request components.
        Enforces Rule 5 for detecting conflicting submissions under identical keys.
        """
        normalized_outcomes = [
            {
                "station_id": o.station_id,
                "predicted_arrivals": round(float(o.predicted_arrivals), 4),
                "estimated_served": round(float(o.estimated_served), 4),
                "estimated_unserved": round(float(o.estimated_unserved), 4),
                "allocated_power_kw": round(float(o.allocated_power_kw), 4),
                "deferred_vehicles": round(float(o.deferred_vehicles), 4),
                "deferred_energy_kwh": round(float(o.deferred_energy_kwh), 4),
            }
            for o in sorted(outcomes, key=lambda x: x.station_id)
        ]
        canonical_dict = {
            "allocation_id": allocation_id,
            "deferred_fraction": round(float(deferred_fraction), 4),
            "station_outcomes": normalized_outcomes,
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

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

        # Extract current station outcomes from persisted allocation results
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

        payload_hash = self.compute_payload_fingerprint(allocation_id, deferred_fraction, outcomes)

        # Rule 4: One feedback submission permitted per allocation run
        existing_by_alloc = self.feedback_repo.get_by_allocation_id(allocation_id)
        if existing_by_alloc:
            if existing_by_alloc.idempotency_key != idempotency_key:
                raise IdempotencyConflictError(
                    f"Feedback has already been submitted for allocation run '{allocation_id}' with idempotency key "
                    f"'{existing_by_alloc.idempotency_key}'. Only one feedback submission is permitted per allocation run.",
                    idempotency_key=idempotency_key,
                )

        # Rule 1, 2, 3: Enforce Idempotency & Conflict logic via key lookup
        existing = self.feedback_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            # Rule 3: Conflicting payload with the same idempotency key
            if existing.allocation_id != allocation_id or (existing.payload_hash and existing.payload_hash != payload_hash):
                raise IdempotencyConflictError(
                    f"Idempotency key '{idempotency_key}' was previously used for a different request payload or allocation run.",
                    idempotency_key=idempotency_key,
                )

            # Rule 1: Identical retry of already succeeded submission -> return cached record
            if existing.submission_status == "submitted":
                adj = self.adjustment_repo.get_by_source_feedback(existing.feedback_id)
                if not adj:
                    provider = get_forecast_provider()
                    target_feedback_id = self.resolve_remote_feedback_id(existing.feedback_id) or existing.feedback_id
                    interval_duration = allocation.interval_end - allocation.interval_start
                    target_start = allocation.interval_end
                    target_end = target_start + interval_duration
                    adj_response = None
                    try:
                        adj_response = provider.get_next_operational_adjustment(
                            feedback_id=target_feedback_id,
                            target_interval_start=target_start.isoformat(),
                            target_interval_end=target_end.isoformat(),
                            forecast_id=existing.forecast_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to retrieve operational adjustment during identical retry for %s: %s",
                            existing.feedback_id,
                            exc,
                        )
                    if adj_response:
                        adjustment_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
                        assumptions = adj_response.get("calculation_assumptions", {}) or {}
                        remote_fid = self.resolve_remote_feedback_id(existing.feedback_id)
                        if remote_fid:
                            assumptions["remote_feedback_id"] = remote_fid
                        adj_data = {
                            "operational_adjustment_id": adjustment_id,
                            "source_feedback_id": existing.feedback_id,
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
                            "calculation_assumptions_json": json.dumps(assumptions),
                        }
                        adj = self.adjustment_repo.create(adj_data)
                return self._build_response(existing, adj.operational_adjustment_id if adj else None)

            # Rule 2: Previously failed submission -> allow safe retry using the same idempotency key
            provider = get_forecast_provider()
            new_retry_count = (existing.retry_count or 0) + 1
            outcomes_raw = json.loads(existing.station_outcomes_json)
            payload = {
                "feedback_id": existing.feedback_id,
                "scenario_id": existing.scenario_id,
                "forecast_id": existing.forecast_id,
                "allocation_id": existing.allocation_id,
                "outcome_kind": existing.outcome_kind,
                "interval_start": existing.interval_start.isoformat() if isinstance(existing.interval_start, datetime) else str(existing.interval_start),
                "interval_end": existing.interval_end.isoformat() if isinstance(existing.interval_end, datetime) else str(existing.interval_end),
                "deferred_fraction": existing.deferred_fraction,
                "station_outcomes": outcomes_raw,
            }

            retry_status = "submitted"
            retry_error = None
            remote_feedback_id = None
            try:
                feedback_result = provider.submit_feedback(payload)
                if isinstance(feedback_result, dict):
                    remote_feedback_id = feedback_result.get("remote_feedback_id") or feedback_result.get("feedback_id")
            except IdempotencyConflictError:
                raise
            except ProviderIntegrationError as pie:
                retry_status = "failed"
                retry_error = pie.message
            except Exception as exc:
                retry_status = "failed"
                retry_error = str(exc)

            existing = self.feedback_repo.update_status(
                record=existing,
                status=retry_status,
                retry_count=new_retry_count,
                error_details=retry_error,
            )

            adjustment_id: Optional[str] = None
            adjustment_error: Optional[str] = None
            if retry_status == "submitted":
                existing_adj = self.adjustment_repo.get_by_source_feedback(existing.feedback_id)
                if existing_adj:
                    adjustment_id = existing_adj.operational_adjustment_id
                else:
                    interval_duration = allocation.interval_end - allocation.interval_start
                    target_start = allocation.interval_end
                    target_end = target_start + interval_duration
                    target_feedback_id = remote_feedback_id or self.resolve_remote_feedback_id(existing.feedback_id) or existing.feedback_id
                    try:
                        adj_response = provider.get_next_operational_adjustment(
                            feedback_id=target_feedback_id,
                            target_interval_start=target_start.isoformat(),
                            target_interval_end=target_end.isoformat(),
                            forecast_id=existing.forecast_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to retrieve operational adjustment for retried feedback %s: %s",
                            existing.feedback_id,
                            exc,
                        )
                        adjustment_error = f"{exc.__class__.__name__}: {str(exc)}"
                        adj_response = None

                    if adj_response:
                        adjustment_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
                        assumptions = adj_response.get("calculation_assumptions", {}) or {}
                        resolved_remote = remote_feedback_id or self.resolve_remote_feedback_id(existing.feedback_id)
                        if resolved_remote:
                            assumptions["remote_feedback_id"] = resolved_remote
                        adj_data = {
                            "operational_adjustment_id": adjustment_id,
                            "source_feedback_id": existing.feedback_id,
                            "parent_forecast_id": allocation.forecast_id,
                            "target_interval_start": target_start,
                            "target_interval_end": target_end,
                            "station_adjustments_json": json.dumps(adj_response.get("station_adjustments", [])),
                            "deferred_demand_contribution_json": json.dumps([
                                {
                                    "station_id": o["station_id"],
                                    "deferred_vehicles": o.get("deferred_vehicles", 0.0),
                                    "deferred_energy_kwh": o.get("deferred_energy_kwh", 0.0),
                                }
                                for o in outcomes_raw
                            ]),
                            "calculation_assumptions_json": json.dumps(assumptions),
                        }
                        self.adjustment_repo.create(adj_data)

            self.audit_repo.log(
                event_type="FEEDBACK_RETRIED",
                entity_type="FeedbackRecord",
                entity_id=existing.feedback_id,
                action="RETRY",
                details={
                    "status": retry_status,
                    "retry_count": new_retry_count,
                    "allocation_id": allocation_id,
                    "adjustment_id": adjustment_id,
                    "remote_feedback_id": remote_feedback_id or self.resolve_remote_feedback_id(existing.feedback_id),
                    "adjustment_error": adjustment_error,
                },
            )

            return self._build_response(existing, adjustment_id)

        # 3. New submission workflow
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

        provider = get_forecast_provider()
        submission_status = "submitted"
        error_details = None
        remote_feedback_id = None

        try:
            feedback_result = provider.submit_feedback(payload)
            if isinstance(feedback_result, dict):
                remote_feedback_id = feedback_result.get("remote_feedback_id") or feedback_result.get("feedback_id")
        except IdempotencyConflictError:
            raise
        except ProviderIntegrationError as pie:
            submission_status = "failed"
            error_details = pie.message
        except Exception as exc:
            submission_status = "failed"
            error_details = str(exc)

        # 4. Persist feedback record with payload_hash
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
            "payload_hash": payload_hash,
            "retry_count": 0,
            "error_details": error_details,
        }

        try:
            feedback_obj = self.feedback_repo.create(record_data)
        except IntegrityError:
            self.db.rollback()
            # Concurrently created by a competing request
            existing_after_race = self.feedback_repo.get_by_idempotency_key(idempotency_key)
            if existing_after_race:
                adj = self.adjustment_repo.get_by_source_feedback(existing_after_race.feedback_id)
                return self._build_response(existing_after_race, adj.operational_adjustment_id if adj else None)
            raise IdempotencyConflictError(
                f"Concurrent feedback submission conflict for allocation run '{allocation_id}'.",
                idempotency_key=idempotency_key,
            )

        # 5. If successfully submitted, calculate / retrieve operational demand adjustment for next interval
        adjustment_id: Optional[str] = None
        adjustment_error: Optional[str] = None
        if submission_status == "submitted":
            interval_duration = allocation.interval_end - allocation.interval_start
            target_start = allocation.interval_end
            target_end = target_start + interval_duration

            target_feedback_id = remote_feedback_id or feedback_id
            try:
                adj_response = provider.get_next_operational_adjustment(
                    feedback_id=target_feedback_id,
                    target_interval_start=target_start.isoformat(),
                    target_interval_end=target_end.isoformat(),
                    forecast_id=allocation.forecast_id,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to retrieve operational adjustment for feedback %s: %s",
                    feedback_id,
                    exc,
                )
                adjustment_error = f"{exc.__class__.__name__}: {str(exc)}"
                adj_response = None

            if adj_response:
                adjustment_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
                assumptions = adj_response.get("calculation_assumptions", {}) or {}
                if remote_feedback_id:
                    assumptions["remote_feedback_id"] = remote_feedback_id
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
                    "calculation_assumptions_json": json.dumps(assumptions),
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
                "remote_feedback_id": remote_feedback_id,
                "adjustment_error": adjustment_error,
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
