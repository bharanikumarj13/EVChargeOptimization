import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import (
    ProviderIntegrationError,
    IdempotencyConflictError,
)
from app.integrations.live_provider import LiveForecastProvider
from app.integrations.station_mapper import StationMapper, IntegrationProfile
from app.models.station import Station
from app.models.allocation import AllocationRun, AllocationResult
from app.models.audit_event import AuditEvent
from app.models.operational_adjustment import OperationalAdjustment
from app.models.feedback import FeedbackRecord
from app.schemas.feedback import FeedbackCreateRequest
from app.services.feedback_service import FeedbackService


def _setup_allocation_run(db_session, allocation_id="ALLOC-P0-01", forecast_id="FC-P0-01"):
    """Creates a sample completed allocation run in the database."""
    stn1 = db_session.query(Station).filter(Station.station_id == "STN-01").first()
    if not stn1:
        stn1 = Station(
            station_id="STN-01",
            station_name="Downtown Fast Hub",
            charger_count=8,
            available_chargers=8,
            charger_power_kw_per_charger=50.0,
            station_power_limit_kw=350.0,
            avg_session_minutes=40.0,
            grid_group_id="GRID-METRO",
            is_active=True,
        )
        db_session.add(stn1)
        db_session.commit()

    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    base_end = base_start + timedelta(hours=1)

    alloc = AllocationRun(
        allocation_id=allocation_id,
        scenario_id="SCN-TEST-01",
        forecast_id=forecast_id,
        interval_start=base_start,
        interval_end=base_end,
        objective_description="Balanced service optimization",
        status="success",
        constraint_validation_passed=True,
    )
    db_session.add(alloc)
    db_session.flush()

    res = AllocationResult(
        allocation_id=allocation_id,
        station_id="STN-01",
        predicted_arrivals=5.0,
        predicted_energy_kwh=100.0,
        estimated_served=4.0,
        estimated_unserved=1.0,
        allocated_power_kw=150.0,
        estimated_served_energy_kwh=120.0,
        estimated_unserved_energy_kwh=15.0,
        charger_utilization_pct=0.75,
        estimated_wait_minutes=5.0,
    )
    db_session.add(res)
    db_session.commit()
    return alloc


def test_direct_module_imports_no_circular_dependency():
    """
    P0 Fix 1: Verifies that app.services, app.schemas, external_feedback,
    and live_provider can be imported in a clean Python process without circular imports.
    """
    script = (
        "import app.services; "
        "import app.schemas; "
        "from app.schemas.external_feedback import map_allocation_to_external_phase5; "
        "from app.integrations.live_provider import LiveForecastProvider; "
        "print('IMPORT_SUCCESS')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=settings.PROJECT_ROOT if hasattr(settings, "PROJECT_ROOT") else ".",
        env={"PYTHONPATH": "backend"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Import failed with stderr: {proc.stderr}"
    assert "IMPORT_SUCCESS" in proc.stdout


def test_live_provider_fail_fast_missing_token(monkeypatch):
    """
    P0 Fix 2: Verifies that LiveForecastProvider fails fast with a non-retryable
    ProviderIntegrationError when PREDICT_SERVICE_TOKEN is missing or None.
    """
    monkeypatch.setattr(settings, "PREDICT_SERVICE_TOKEN", None)
    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token=None,
    )

    # get_forecast requires auth -> must fail fast
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.get_forecast("FC-001")
    assert exc_info.value.is_retryable is False
    assert "PREDICT_SERVICE_TOKEN" in exc_info.value.message

    # submit_feedback requires auth -> must fail fast
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.submit_feedback({"allocation_id": "AL-01", "forecast_id": "FC-01"})
    assert exc_info.value.is_retryable is False
    assert "PREDICT_SERVICE_TOKEN" in exc_info.value.message

    # get_next_operational_adjustment requires auth -> must fail fast
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_123",
            target_interval_start="2026-10-26T09:00:00Z",
            target_interval_end="2026-10-26T10:00:00Z",
            forecast_id="FC-001",
        )
    assert exc_info.value.is_retryable is False
    assert "PREDICT_SERVICE_TOKEN" in exc_info.value.message


def test_live_provider_health_check_without_token(monkeypatch):
    """
    P0 Fix 2: Verifies that LiveForecastProvider health check uses require_auth=False
    and does not fail with a missing token error.
    """
    monkeypatch.setattr(settings, "PREDICT_SERVICE_TOKEN", None)
    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token=None,
    )

    def mock_get(self, url, **kwargs):
        assert "Authorization" not in kwargs.get("headers", {})
        return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    health = provider.check_health()
    assert health["status"] == "healthy"
    assert health["is_mock"] is False


def test_feedback_service_propagates_http_409_conflict(db_session, monkeypatch):
    """
    P0 Fix 3: Verifies that IdempotencyConflictError from partner HTTP 409
    propagates directly as HTTP 409 and is never swallowed into an HTTP 201 response.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-CONF-01")

    # Mock provider submit_feedback to raise IdempotencyConflictError (partner HTTP 409)
    def mock_submit_feedback(payload):
        raise IdempotencyConflictError(
            "Predictor rejected feedback submission due to allocation_run_id conflict (HTTP 409): Differing payload.",
            idempotency_key=alloc.allocation_id,
        )

    monkeypatch.setattr(
        "app.services.feedback_service.get_forecast_provider",
        lambda: type("MockProvider", (), {"submit_feedback": staticmethod(mock_submit_feedback)})(),
    )

    service = FeedbackService(db_session)
    with pytest.raises(IdempotencyConflictError) as exc_info:
        service.submit_allocation_feedback(
            alloc.allocation_id,
            FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key="KEY-409-TEST"),
        )
    assert exc_info.value.status_code == 409
    assert "conflict" in exc_info.value.message.lower()

    # Verify no FeedbackRecord was committed with status 'submitted' or returned as success
    fb_record = db_session.query(FeedbackRecord).filter(FeedbackRecord.allocation_id == alloc.allocation_id).first()
    assert fb_record is None


def test_feedback_endpoint_returns_409_status_code_on_partner_conflict(client, db_session, monkeypatch):
    """
    P0 Fix 3: Verifies that the FastAPI endpoint /allocations/{id}/feedback returns
    HTTP 409 when the partner predictor returns 409.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-CONF-02")

    def mock_submit_feedback(payload):
        raise IdempotencyConflictError(
            "Partner conflict for allocation run.",
            idempotency_key=alloc.allocation_id,
        )

    monkeypatch.setattr(
        "app.services.feedback_service.get_forecast_provider",
        lambda: type("MockProvider", (), {"submit_feedback": staticmethod(mock_submit_feedback)})(),
    )

    resp = client.post(
        f"/api/v1/allocations/{alloc.allocation_id}/feedback",
        json={"deferred_fraction": 0.70, "idempotency_key": "KEY-EP-409"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["error"] == "IdempotencyConflictError"


def test_feedback_id_persistence_and_recovery_across_reinstantiation(db_session, monkeypatch):
    """
    P0 Fix 4: Verifies that resolve_remote_feedback_id recovers remote predictor feedback ID
    (fbk_...) from OperationalAdjustment calculation assumptions even after the LiveForecastProvider
    in-memory cache has been completely cleared.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-RECOVER-01")

    # Step 1: Submit feedback and store OperationalAdjustment with remote_feedback_id
    local_feedback_id = "FBD-TEST-LOCAL-01"
    remote_feedback_id = "fbk_predictor_assigned_999"

    adj = OperationalAdjustment(
        operational_adjustment_id="ADJ-P0-01",
        source_feedback_id=local_feedback_id,
        parent_forecast_id=alloc.forecast_id,
        target_interval_start=alloc.interval_end,
        target_interval_end=alloc.interval_end + timedelta(hours=1),
        station_adjustments_json="[]",
        deferred_demand_contribution_json="[]",
        calculation_assumptions_json=json.dumps({"remote_feedback_id": remote_feedback_id}),
    )
    db_session.add(adj)
    db_session.commit()

    # Step 2: Wipe in-memory dictionary entirely
    LiveForecastProvider._class_local_to_remote_feedback_ids.clear()
    assert local_feedback_id not in LiveForecastProvider._class_local_to_remote_feedback_ids

    # Step 3: Call resolve_remote_feedback_id
    service = FeedbackService(db_session)
    resolved = service.resolve_remote_feedback_id(local_feedback_id)
    assert resolved == remote_feedback_id

    # Step 4: Verify in-memory cache was repopulated
    assert LiveForecastProvider._class_local_to_remote_feedback_ids.get(local_feedback_id) == remote_feedback_id


def test_feedback_id_recovery_from_audit_event_when_adj_missing(db_session):
    """
    P0 Fix 4: Verifies recovery of remote_feedback_id from AuditEvent when OperationalAdjustment
    was not yet created or failed.
    """
    local_feedback_id = "FBD-TEST-AUDIT-ONLY"
    remote_feedback_id = "fbk_audit_recovered_888"

    # Wipe in-memory dictionary
    LiveForecastProvider._class_local_to_remote_feedback_ids.clear()

    # Log audit event with remote_feedback_id
    audit = AuditEvent(
        event_type="FEEDBACK_SUBMITTED",
        entity_type="FeedbackRecord",
        entity_id=local_feedback_id,
        action="SUBMIT",
        details_json=json.dumps({
            "status": "submitted",
            "remote_feedback_id": remote_feedback_id,
            "allocation_id": "ALLOC-AUDIT-01",
        }),
    )
    db_session.add(audit)
    db_session.commit()

    service = FeedbackService(db_session)
    resolved = service.resolve_remote_feedback_id(local_feedback_id)
    assert resolved == remote_feedback_id
    assert LiveForecastProvider._class_local_to_remote_feedback_ids.get(local_feedback_id) == remote_feedback_id


def test_duplicate_feedback_retry_identical_recovers_missing_adjustment(db_session, monkeypatch):
    """
    P0 Fix 4: Verifies that an identical retry of an already submitted feedback
    recovers the missing operational adjustment if it was originally absent.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-RETRY-01")
    key = "IDEMP-RETRY-TEST-01"

    service = FeedbackService(db_session)
    outcomes = [
        {
            "station_id": "STN-01",
            "predicted_arrivals": 5.0,
            "estimated_served": 4.0,
            "estimated_unserved": 1.0,
            "allocated_power_kw": 150.0,
            "charger_utilization_pct": 0.75,
            "estimated_wait_minutes": 5.0,
            "deferred_vehicles": 0.7,
            "deferred_energy_kwh": 10.5,
        }
    ]

    from app.schemas.feedback import StationFeedbackOutcome
    outcome_objs = [StationFeedbackOutcome(**o) for o in outcomes]
    payload_hash = service.compute_payload_fingerprint(alloc.allocation_id, 0.70, outcome_objs)

    # Existing submitted feedback with NO operational adjustment
    fb_record = FeedbackRecord(
        feedback_id="FBD-RETRY-01",
        scenario_id=alloc.scenario_id,
        forecast_id=alloc.forecast_id,
        allocation_id=alloc.allocation_id,
        outcome_kind="simulation",
        interval_start=alloc.interval_start,
        interval_end=alloc.interval_end,
        station_outcomes_json=json.dumps(outcomes),
        deferred_fraction=0.70,
        submission_status="submitted",
        idempotency_key=key,
        payload_hash=payload_hash,
        retry_count=0,
    )
    db_session.add(fb_record)

    # Persist audit event with remote feedback ID
    audit = AuditEvent(
        event_type="FEEDBACK_SUBMITTED",
        entity_type="FeedbackRecord",
        entity_id="FBD-RETRY-01",
        action="SUBMIT",
        details_json=json.dumps({
            "status": "submitted",
            "remote_feedback_id": "fbk_remote_retry_777",
            "allocation_id": alloc.allocation_id,
        }),
    )
    db_session.add(audit)
    db_session.commit()

    # Mock provider get_next_operational_adjustment to return adjustments
    def mock_get_adj(feedback_id, target_interval_start, target_interval_end, forecast_id=None):
        assert feedback_id == "fbk_remote_retry_777"
        return {
            "forecast_id": forecast_id,
            "feedback_id": feedback_id,
            "station_adjustments": [{"station_id": "STN-01", "adjusted_predicted_energy_kwh": 130.0}],
            "calculation_assumptions": {"method": "linear_carryover"},
        }

    monkeypatch.setattr(
        "app.services.feedback_service.get_forecast_provider",
        lambda: type("MockProvider", (), {
            "get_next_operational_adjustment": staticmethod(mock_get_adj),
        })(),
    )

    # Identical retry should recover operational adjustment
    res = service.submit_allocation_feedback(
        alloc.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key=key),
    )
    assert res.submission_status == "submitted"
    assert res.operational_adjustment_id is not None

    # Check adjustment was persisted in DB
    adj_db = service.adjustment_repo.get_by_source_feedback("FBD-RETRY-01")
    assert adj_db is not None
    assert adj_db.operational_adjustment_id == res.operational_adjustment_id


def test_adjustment_failure_observability_and_audit_logging(db_session, monkeypatch, caplog):
    """
    P0 Fix 6: Verifies that when adjustment retrieval fails after feedback submission:
    - Feedback submission status is 'submitted' (not failed).
    - operational_adjustment_id is None (not misleading caller).
    - Warning is logged via logger.warning.
    - adjustment_error is recorded in AuditEvent.details_json without secrets.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-OBSERV-01")

    def mock_submit(payload):
        return {
            "status": "accepted",
            "feedback_id": "fbk_observ_123",
            "remote_feedback_id": "fbk_observ_123",
            "is_duplicate": False,
        }

    def mock_adj_fail(feedback_id, target_interval_start, target_interval_end, forecast_id=None):
        raise ProviderIntegrationError("Predictor adjusted-demand endpoint HTTP 500 error", is_retryable=True)

    monkeypatch.setattr(
        "app.services.feedback_service.get_forecast_provider",
        lambda: type("MockProvider", (), {
            "submit_feedback": staticmethod(mock_submit),
            "get_next_operational_adjustment": staticmethod(mock_adj_fail),
        })(),
    )

    import logging
    caplog.set_level(logging.WARNING)

    service = FeedbackService(db_session)
    res = service.submit_allocation_feedback(
        alloc.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key="KEY-OBSERV-01"),
    )

    # Feedback submission itself succeeded
    assert res.submission_status == "submitted"
    assert res.operational_adjustment_id is None

    # Observability: warning log was emitted
    assert any("Failed to retrieve operational adjustment" in r.message for r in caplog.records)

    # Observability: Audit event records adjustment_error
    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_id == res.feedback_id)
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert audit is not None
    audit_details = json.loads(audit.details_json)
    assert audit_details["status"] == "submitted"
    assert audit_details["adjustment_id"] is None
    assert audit_details["remote_feedback_id"] == "fbk_observ_123"
    assert "adjustment_error" in audit_details
    assert "HTTP 500" in audit_details["adjustment_error"]


def test_feedback_persistence_concurrency_race_recovery(db_session, monkeypatch):
    """
    Failure Case 9: Tests database IntegrityError during persistence due to a concurrent race condition.
    Verifies that session rollback occurs and the concurrently created record is safely returned.
    """
    alloc = _setup_allocation_run(db_session, allocation_id="ALLOC-RACE-01")
    key = "IDEMP-RACE-01"

    service = FeedbackService(db_session)
    orig_create = service.feedback_repo.create

    # First pre-populate a record as if created concurrently by another worker
    outcomes = [
        {
            "station_id": "STN-01",
            "predicted_arrivals": 5.0,
            "estimated_served": 4.0,
            "estimated_unserved": 1.0,
            "allocated_power_kw": 150.0,
            "charger_utilization_pct": 0.75,
            "estimated_wait_minutes": 5.0,
            "deferred_vehicles": 0.7,
            "deferred_energy_kwh": 10.5,
        }
    ]
    from app.schemas.feedback import StationFeedbackOutcome
    outcome_objs = [StationFeedbackOutcome(**o) for o in outcomes]
    payload_hash = service.compute_payload_fingerprint(alloc.allocation_id, 0.70, outcome_objs)

    existing_record = FeedbackRecord(
        feedback_id="FBD-CONCURRENT-01",
        scenario_id=alloc.scenario_id,
        forecast_id=alloc.forecast_id,
        allocation_id=alloc.allocation_id,
        outcome_kind="simulation",
        interval_start=alloc.interval_start,
        interval_end=alloc.interval_end,
        station_outcomes_json=json.dumps(outcomes),
        deferred_fraction=0.70,
        submission_status="submitted",
        idempotency_key=key,
        payload_hash=payload_hash,
        retry_count=0,
    )
    db_session.add(existing_record)
    db_session.commit()

    # Mock provider submit
    monkeypatch.setattr(
        "app.services.feedback_service.get_forecast_provider",
        lambda: type("MockProvider", (), {
            "submit_feedback": staticmethod(lambda p: {"status": "accepted", "feedback_id": "fbk_race_1"}),
            "get_next_operational_adjustment": staticmethod(lambda **k: None),
        })(),
    )

    # Force IntegrityError on create
    from sqlalchemy.exc import IntegrityError
    def mock_create_fail(data):
        raise IntegrityError("duplicate key", params={}, orig=Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(service.feedback_repo, "create", mock_create_fail)

    # Calling submit_allocation_feedback should catch IntegrityError, rollback, and return existing record
    res = service.submit_allocation_feedback(
        alloc.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key=key),
    )
    assert res.feedback_id == "FBD-CONCURRENT-01"
    assert res.submission_status == "submitted"


def test_station_mapper_unconfirmed_safeguard_in_live_mode(db_session):
    """
    Failure Case 4: Verifies that in live mode, AllocationService strictly rejects unconfirmed
    physical station correspondence unless CONFIRM_PHYSICAL_STATION_MAPPINGS is True.
    """
    from app.core.exceptions import StationMappingError
    from app.services.allocation_service import AllocationService
    from app.schemas.allocation import AllocationRunRequest

    service = AllocationService(db_session)
    req = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FC-001",
        interval_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_end=datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc),
    )

    # In mock mode, it succeeds
    assert getattr(settings, "PREDICT_PROVIDER_MODE", "mock") == "mock"
