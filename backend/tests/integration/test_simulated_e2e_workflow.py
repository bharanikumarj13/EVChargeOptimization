import json
from datetime import datetime, timezone, timedelta
import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import InvalidForecastError, IdempotencyConflictError
from app.integrations.live_provider import LiveForecastProvider
from app.integrations.station_mapper import StationMapper, IntegrationProfile
from app.models.station import Station
from app.models.scenario import Scenario
from app.models.operational_adjustment import OperationalAdjustment
from app.schemas.allocation import AllocationRunRequest
from app.schemas.feedback import FeedbackCreateRequest, StationFeedbackOutcome, FeedbackResponse
from app.schemas.forecast import ForecastResponse, ForecastIntervalItem
from app.services.allocation_service import AllocationService
from app.services.feedback_service import FeedbackService


def _ensure_three_stations(db_session):
    """Ensures STN-01, STN-02, and STN-03 are present in the test database."""
    stn3 = db_session.query(Station).filter(Station.station_id == "STN-03").first()
    if not stn3:
        stn3 = Station(
            station_id="STN-03",
            station_name="Suburban Retail Plaza",
            charger_count=6,
            available_chargers=6,
            charger_power_kw_per_charger=50.0,
            station_power_limit_kw=250.0,
            avg_session_minutes=45.0,
            grid_group_id="GRID-SUBURB",
            is_active=True,
        )
        db_session.add(stn3)
        db_session.commit()


@pytest.fixture
def three_station_context(db_session):
    _ensure_three_stations(db_session)
    orig_profile = StationMapper.get_profile()
    StationMapper.set_profile(IntegrationProfile.THREE_STATION_INTEGRATION.value)
    try:
        yield db_session
    finally:
        StationMapper.set_profile(orig_profile)


def test_allocation_service_exact_interval_boundaries(three_station_context, monkeypatch):
    """
    Verifies that AllocationService enforces exact boundary matching in UTC:
    - Timezone-equivalent timestamps are accepted.
    - 30-second deviations are strictly rejected with InvalidForecastError.
    - interval_start >= interval_end is rejected.
    """
    db_session = three_station_context
    service = AllocationService(db_session)

    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    base_end = base_start + timedelta(hours=1)

    # Mock provider returning exact interval
    mock_forecast = ForecastResponse(
        forecast_id="FCST-EXACT-01",
        scenario_id="SCN-TEST-01",
        model_version="1.0",
        generated_at=datetime.now(timezone.utc),
        station_ids=["STN-01", "STN-02", "STN-03"],
        interval_count=3,
        intervals=[
            ForecastIntervalItem(
                forecast_id="FCST-EXACT-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-01",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=5.0,
                predicted_energy_kwh=80.0,
                generated_at=datetime.now(timezone.utc),
            ),
            ForecastIntervalItem(
                forecast_id="FCST-EXACT-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-02",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=4.0,
                predicted_energy_kwh=60.0,
                generated_at=datetime.now(timezone.utc),
            ),
            ForecastIntervalItem(
                forecast_id="FCST-EXACT-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-03",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=3.0,
                predicted_energy_kwh=50.0,
                generated_at=datetime.now(timezone.utc),
            ),
        ],
    )

    class MockProvider:
        def get_forecast(self, fid, scn):
            return mock_forecast

    monkeypatch.setattr("app.services.allocation_service.get_forecast_provider", lambda: MockProvider())

    # 1. Exact UTC match succeeds
    req_exact = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-EXACT-01",
        interval_start=base_start,
        interval_end=base_end,
        operational_adjustment_id=None,
    )
    res_exact = service.run_allocation(req_exact)
    assert res_exact.status == "success"
    assert res_exact.constraint_validation_passed is True

    # 2. Timezone-equivalent offset (+05:30 = 13:30:00) matches base_start (08:00:00Z)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    req_tz_eq = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-EXACT-01",
        interval_start=base_start.astimezone(ist_tz),
        interval_end=base_end.astimezone(ist_tz),
        operational_adjustment_id=None,
    )
    res_tz_eq = service.run_allocation(req_tz_eq)
    assert res_tz_eq.status == "success"

    # 3. 30-second boundary deviation must be rejected
    req_slight_dev = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-EXACT-01",
        interval_start=base_start + timedelta(seconds=30),
        interval_end=base_end,
        operational_adjustment_id=None,
    )
    with pytest.raises(InvalidForecastError) as exc_info:
        service.run_allocation(req_slight_dev)
    assert "Both start and end timestamps must exactly match a valid forecast interval" in exc_info.value.message

    # 4. Invalid interval order (start >= end)
    req_inverted = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-EXACT-01",
        interval_start=base_end,
        interval_end=base_start,
        operational_adjustment_id=None,
    )
    with pytest.raises(InvalidForecastError) as exc_info_inv:
        service.run_allocation(req_inverted)
    assert "must be strictly before interval end" in exc_info_inv.value.message


def test_allocation_service_operational_adjustment_validation(three_station_context, monkeypatch):
    """
    Verifies that AllocationService validates both target interval boundaries
    and parent_forecast_id when an operational_adjustment_id is provided.
    """
    db_session = three_station_context
    service = AllocationService(db_session)

    t1_start = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    t1_end = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)

    # Create an operational adjustment in DB
    adj = OperationalAdjustment(
        operational_adjustment_id="ADJ-VAL-TEST-01",
        source_feedback_id="FBD-VAL-TEST-01",
        parent_forecast_id="FCST-PARENT-01",
        target_interval_start=t1_start,
        target_interval_end=t1_end,
        station_adjustments_json=json.dumps([
            {"station_id": "STN-01", "adjusted_predicted_arrivals": 5.0, "adjusted_predicted_energy_kwh": 75.0},
            {"station_id": "STN-02", "adjusted_predicted_arrivals": 4.0, "adjusted_predicted_energy_kwh": 55.0},
            {"station_id": "STN-03", "adjusted_predicted_arrivals": 3.0, "adjusted_predicted_energy_kwh": 45.0},
        ]),
        deferred_demand_contribution_json=json.dumps([]),
        calculation_assumptions_json=json.dumps({"remote_feedback_id": "fbk_remote_val_01"}),
    )
    db_session.add(adj)
    db_session.commit()

    class DummyProvider:
        def get_forecast(self, fid, scn):
            return ForecastResponse(
                forecast_id=fid,
                scenario_id=scn or "SCN-TEST-01",
                model_version="1.0",
                generated_at=datetime.now(timezone.utc),
                station_ids=["STN-01", "STN-02", "STN-03"],
                interval_count=0,
                intervals=[],
            )

    monkeypatch.setattr("app.services.allocation_service.get_forecast_provider", lambda: DummyProvider())

    # 1. Matching interval and parent_forecast_id succeeds
    req_valid = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-PARENT-01",
        interval_start=t1_start,
        interval_end=t1_end,
        operational_adjustment_id="ADJ-VAL-TEST-01",
    )
    res_valid = service.run_allocation(req_valid)
    assert res_valid.status == "success"
    assert res_valid.operational_adjustment_id == "ADJ-VAL-TEST-01"

    # 2. Mismatched interval start/end raises InvalidForecastError
    req_wrong_interval = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-PARENT-01",
        interval_start=t1_start + timedelta(hours=1),
        interval_end=t1_end + timedelta(hours=1),
        operational_adjustment_id="ADJ-VAL-TEST-01",
    )
    with pytest.raises(InvalidForecastError) as exc_int:
        service.run_allocation(req_wrong_interval)
    assert "does not match requested interval" in exc_int.value.message

    # 3. Mismatched parent_forecast_id raises InvalidForecastError
    req_wrong_forecast = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FCST-DIFFERENT-PARENT",
        interval_start=t1_start,
        interval_end=t1_end,
        operational_adjustment_id="ADJ-VAL-TEST-01",
    )
    with pytest.raises(InvalidForecastError) as exc_fc:
        service.run_allocation(req_wrong_forecast)
    assert "which does not match requested forecast" in exc_fc.value.message


def test_feedback_service_passes_remote_feedback_id_and_persists_in_assumptions(three_station_context, monkeypatch):
    """
    Verifies that FeedbackService extracts remote_feedback_id from the provider submission response,
    passes it directly into get_next_operational_adjustment, and persists it inside
    OperationalAdjustment.calculation_assumptions_json and audit log.
    """
    db_session = three_station_context
    feedback_service = FeedbackService(db_session)
    alloc_service = AllocationService(db_session)

    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    base_end = base_start + timedelta(hours=1)

    mock_forecast = ForecastResponse(
        forecast_id="FCST-REMOTE-ID-01",
        scenario_id="SCN-TEST-01",
        model_version="1.0",
        generated_at=datetime.now(timezone.utc),
        station_ids=["STN-01", "STN-02", "STN-03"],
        interval_count=3,
        intervals=[
            ForecastIntervalItem(
                forecast_id="FCST-REMOTE-ID-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-01",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=5.0,
                predicted_energy_kwh=80.0,
                generated_at=datetime.now(timezone.utc),
            ),
            ForecastIntervalItem(
                forecast_id="FCST-REMOTE-ID-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-02",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=4.0,
                predicted_energy_kwh=60.0,
                generated_at=datetime.now(timezone.utc),
            ),
            ForecastIntervalItem(
                forecast_id="FCST-REMOTE-ID-01",
                scenario_id="SCN-TEST-01",
                station_id="STN-03",
                interval_start=base_start,
                interval_end=base_end,
                interval_minutes=60,
                predicted_arrivals=3.0,
                predicted_energy_kwh=50.0,
                generated_at=datetime.now(timezone.utc),
            ),
        ],
    )

    class MockLiveProvider:
        def __init__(self):
            self.passed_feedback_id = None

        def get_forecast(self, fid, scn):
            return mock_forecast

        def submit_feedback(self, payload):
            return {
                "status": "accepted",
                "feedback_id": "fbk_remote_pred_888",
                "remote_feedback_id": "fbk_remote_pred_888",
                "allocation_run_id": payload.get("allocation_id"),
                "forecast_id": payload.get("forecast_id"),
                "is_duplicate": False,
            }

        def get_next_operational_adjustment(self, feedback_id, target_interval_start, target_interval_end, forecast_id):
            self.passed_feedback_id = feedback_id
            return {
                "operational_adjustment_id": f"ADJ-{feedback_id[:8]}",
                "station_adjustments": [
                    {"station_id": "STN-01", "adjusted_predicted_arrivals": 5.0, "adjusted_predicted_energy_kwh": 70.0},
                    {"station_id": "STN-02", "adjusted_predicted_arrivals": 4.0, "adjusted_predicted_energy_kwh": 50.0},
                    {"station_id": "STN-03", "adjusted_predicted_arrivals": 3.0, "adjusted_predicted_energy_kwh": 40.0},
                ],
                "calculation_assumptions": {"policy": "unserved_deferral"},
            }

    provider_instance = MockLiveProvider()
    monkeypatch.setattr("app.services.allocation_service.get_forecast_provider", lambda: provider_instance)
    monkeypatch.setattr("app.services.feedback_service.get_forecast_provider", lambda: provider_instance)

    alloc_run = alloc_service.run_allocation(
        AllocationRunRequest(
            scenario_id="SCN-TEST-01",
            forecast_id="FCST-REMOTE-ID-01",
            interval_start=base_start,
            interval_end=base_end,
        )
    )

    fb_resp = feedback_service.submit_allocation_feedback(
        allocation_id=alloc_run.allocation_id,
        req=FeedbackCreateRequest(
            deferred_fraction=0.75,
            idempotency_key=f"IDEMP-REMOTE-TEST-{alloc_run.allocation_id}",
        ),
    )

    # 1. Assert get_next_operational_adjustment was called with predictor remote_feedback_id
    assert provider_instance.passed_feedback_id == "fbk_remote_pred_888"

    # 2. Assert OperationalAdjustment calculation_assumptions_json stores remote_feedback_id
    assert fb_resp.operational_adjustment_id is not None
    adj = (
        db_session.query(OperationalAdjustment)
        .filter(OperationalAdjustment.operational_adjustment_id == fb_resp.operational_adjustment_id)
        .first()
    )
    assert adj is not None
    assumptions = json.loads(adj.calculation_assumptions_json)
    assert assumptions.get("remote_feedback_id") == "fbk_remote_pred_888"


def test_simulated_e2e_integration_workflow(three_station_context, monkeypatch):
    """
    Executes the full 6-step EVCharge-Opt <-> EVCharge-Predict simulated integration workflow:
    1. Retrieve predictor forecast through authenticated backend API (contract structure).
    2. Map canonical station IDs (ST-001..003 -> STN-01..03) and 6 nested hourly intervals.
    3. Run optimizer for Interval 1 under physical and grid constraints.
    4. Submit allocation feedback to POST /api/v1/feedback (supporting partial intervals, idempotency, conflict).
    5. Retrieve adjusted operational demand for Interval 2 using predictor feedback_id.
    6. Run subsequent allocation for Interval 2 and verify structured run summary.
    """
    db_session = three_station_context
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    base_url = "https://evcharge-predict.onrender.com"
    service_token = "simulated_e2e_bearer_token_xyz"

    forecast_id = "fcst_contract_e2e_01"
    predictor_feedback_id = "fbk_e2e_contract_9988"

    # 1. Prepare simulated contract forecast response (6 intervals for ST-001, ST-002, ST-003)
    def _create_station_forecast(canonical_stn: str, base_arrivals: float, base_kwh: float):
        intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            intervals.append({
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "predicted_arrivals": round(base_arrivals + i * 0.5, 1),
                "predicted_energy_kwh": round(base_kwh + i * 10.0, 1),
                "confidence_score": 0.94,
            })
        return {"station_id": canonical_stn, "intervals": intervals}

    simulated_remote_forecast = {
        "contract_version": "1.0",
        "forecast_id": forecast_id,
        "scenario_id": "scenario_contract_sim",
        "generated_at": (base_start - timedelta(minutes=15)).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [
            _create_station_forecast("ST-001", 6.0, 90.0),
            _create_station_forecast("ST-002", 4.0, 60.0),
            _create_station_forecast("ST-003", 3.0, 45.0),
        ],
        "model": {
            "model_version": "predict-v2.4",
            "training_data_type": "synthetic",
        },
    }

    submitted_feedbacks = {}
    auth_headers_captured = []

    def mock_http_handler(request: httpx.Request) -> httpx.Response:
        auth_hdr = request.headers.get("Authorization")
        if auth_hdr:
            auth_headers_captured.append(auth_hdr)

        # Step 1: GET /api/v1/forecasts/{id}
        if request.method == "GET" and f"/api/v1/forecasts/{forecast_id}" in str(request.url) and "adjusted-demand" not in str(request.url):
            assert auth_hdr == f"Bearer {service_token}", "Step 1: Authorization header missing or incorrect"
            return httpx.Response(200, json=simulated_remote_forecast, request=request)

        # Step 4: POST /api/v1/feedback
        if request.method == "POST" and "/api/v1/feedback" in str(request.url):
            assert auth_hdr == f"Bearer {service_token}", "Step 4: Authorization header missing or incorrect"
            body = json.loads(request.content.decode("utf-8"))
            alloc_run_id = body.get("allocation_run_id")

            # Check for conflict: same allocation_run_id but different station outcomes
            if alloc_run_id in submitted_feedbacks:
                prev_stations = submitted_feedbacks[alloc_run_id].get("stations")
                curr_stations = body.get("stations")
                if prev_stations == curr_stations:
                    # Idempotent retry: HTTP 200 with is_duplicate = True
                    return httpx.Response(
                        200,
                        json={
                            "contract_version": "1.0",
                            "feedback_id": predictor_feedback_id,
                            "allocation_run_id": alloc_run_id,
                            "forecast_id": forecast_id,
                            "scenario_id": body.get("scenario_id", "scenario_contract_sim"),
                            "status": "accepted",
                            "is_duplicate": True,
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "feedback_url": f"/api/v1/feedback/{predictor_feedback_id}",
                        },
                        request=request,
                    )
                else:
                    # Differing payload: HTTP 409
                    return httpx.Response(
                        409,
                        json={"detail": f"Conflict: allocation_run_id '{alloc_run_id}' previously submitted with different payload."},
                        request=request,
                    )

            submitted_feedbacks[alloc_run_id] = body
            return httpx.Response(
                201,
                json={
                    "contract_version": "1.0",
                    "feedback_id": predictor_feedback_id,
                    "allocation_run_id": alloc_run_id,
                    "forecast_id": forecast_id,
                    "scenario_id": body.get("scenario_id", "scenario_contract_sim"),
                    "status": "accepted",
                    "is_duplicate": False,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "feedback_url": f"/api/v1/feedback/{predictor_feedback_id}",
                },
                request=request,
            )

        # Step 5: GET /api/v1/forecasts/{id}/adjusted-demand?feedback_id=...
        if request.method == "GET" and "adjusted-demand" in str(request.url):
            assert auth_hdr == f"Bearer {service_token}", "Step 5: Authorization header missing or incorrect"
            target_inv_start = base_start + timedelta(hours=1)
            target_inv_end = target_inv_start + timedelta(hours=1)
            adjusted_payload = {
                "contract_version": "1.0",
                "forecast_id": forecast_id,
                "scenario_id": "scenario_contract_sim",
                "feedback_id": predictor_feedback_id,
                "allocation_run_id": "ALC-INTERVAL-1",
                "demand_type": "feedback-adjusted-operational",
                "adjustment_policy_version": "v1.0",
                "policy_description": "Unserved demand from Interval 1 added to Interval 2",
                "policy_limitations": "Linear redistribution",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "stations": [
                    {
                        "station_id": "ST-001",
                        "intervals": [{
                            "interval_start": target_inv_start.isoformat(),
                            "interval_end": target_inv_end.isoformat(),
                            "baseline_arrivals": 6,
                            "baseline_energy_kwh": 100.0,
                            "adjusted_operational_demand_kwh": 105.0,  # +5 kWh adjusted
                            "adjustment_status": "adjusted",
                        }],
                    },
                    {
                        "station_id": "ST-002",
                        "intervals": [{
                            "interval_start": target_inv_start.isoformat(),
                            "interval_end": target_inv_end.isoformat(),
                            "baseline_arrivals": 4,
                            "baseline_energy_kwh": 70.0,
                            "adjusted_operational_demand_kwh": 70.0,
                            "adjustment_status": "unchanged",
                        }],
                    },
                    {
                        "station_id": "ST-003",
                        "intervals": [{
                            "interval_start": target_inv_start.isoformat(),
                            "interval_end": target_inv_end.isoformat(),
                            "baseline_arrivals": 3,
                            "baseline_energy_kwh": 55.0,
                            "adjusted_operational_demand_kwh": 57.0,  # +2 kWh adjusted
                            "adjustment_status": "adjusted",
                        }],
                    },
                ],
            }
            return httpx.Response(200, json=adjusted_payload, request=request)

        return httpx.Response(404, json={"detail": "Not found"}, request=request)

    def mock_send(self, request, *args, **kwargs):
        return mock_http_handler(request)

    monkeypatch.setattr(httpx.Client, "send", mock_send)

    # Initialize live provider
    live_provider = LiveForecastProvider(
        base_url=base_url,
        service_token=service_token,
        timeout=10.0,
    )
    monkeypatch.setattr("app.services.allocation_service.get_forecast_provider", lambda: live_provider)
    monkeypatch.setattr("app.services.feedback_service.get_forecast_provider", lambda: live_provider)

    # -------------------------------------------------------------------------
    # STEP 1: Retrieve predictor forecast through authenticated backend-to-backend API
    # -------------------------------------------------------------------------
    forecast = live_provider.get_forecast(forecast_id=forecast_id)
    assert forecast.forecast_id == forecast_id
    assert any(h == f"Bearer {service_token}" for h in auth_headers_captured)

    # -------------------------------------------------------------------------
    # STEP 2: Map canonical station IDs & nested intervals into EVCharge-Opt format
    # -------------------------------------------------------------------------
    assert set(forecast.station_ids) == {"STN-01", "STN-02", "STN-03"}
    # 3 stations * 6 hourly intervals = 18 intervals
    assert len(forecast.intervals) == 18
    # Validate each station has 6 consecutive intervals
    for stn_id in ["STN-01", "STN-02", "STN-03"]:
        stn_intervals = [i for i in forecast.intervals if i.station_id == stn_id]
        assert len(stn_intervals) == 6
        for idx in range(5):
            assert stn_intervals[idx].interval_end == stn_intervals[idx + 1].interval_start

    # -------------------------------------------------------------------------
    # STEP 3: Run existing optimizer for Interval 1 under constraints
    # -------------------------------------------------------------------------
    alloc_service = AllocationService(db_session)
    interval_1_req = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id=forecast_id,
        interval_start=base_start,
        interval_end=base_start + timedelta(hours=1),
        operational_adjustment_id=None,
    )
    alloc_1 = alloc_service.run_allocation(interval_1_req)
    assert alloc_1.status == "success"
    assert alloc_1.constraint_validation_passed is True
    assert len(alloc_1.results) == 3

    # Verify physical bounds
    total_allocated_kw = sum(r.allocated_power_kw for r in alloc_1.results)
    assert total_allocated_kw > 0.0
    for res in alloc_1.results:
        assert res.allocated_power_kw >= 0.0
        assert res.charger_utilization_pct <= 100.0

    # -------------------------------------------------------------------------
    # STEP 4: Submit allocation feedback to POST /api/v1/feedback
    # -------------------------------------------------------------------------
    feedback_service = FeedbackService(db_session)
    fb_res = feedback_service.submit_allocation_feedback(
        allocation_id=alloc_1.allocation_id,
        req=FeedbackCreateRequest(
            deferred_fraction=0.70,
            idempotency_key=f"IDEMP-E2E-{alloc_1.allocation_id}",
        ),
    )
    assert fb_res.submission_status == "submitted"
    assert fb_res.operational_adjustment_id is not None
    local_feedback_id = fb_res.feedback_id

    # Verify Idempotency: identical retry returns HTTP 200 with is_duplicate = True
    raw_payload_retry = {
        "allocation_id": alloc_1.allocation_id,
        "forecast_id": forecast_id,
        "scenario_id": "SCN-TEST-01",
        "local_feedback_id": local_feedback_id,
        "interval_start": base_start.isoformat(),
        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
        "station_outcomes": [
            {
                "station_id": r.station_id,
                "allocated_energy_kwh": r.estimated_served_energy_kwh,
                "available_capacity_kw": r.allocated_power_kw,
                "reported_unmet_demand_kwh": r.estimated_unserved_energy_kwh,
            }
            for r in alloc_1.results
        ],
    }
    retry_ack = live_provider.submit_feedback(raw_payload_retry)
    assert retry_ack["is_duplicate"] is True
    assert retry_ack["feedback_id"] == predictor_feedback_id

    # Verify Conflict: differing payload for same allocation_run_id raises IdempotencyConflictError (HTTP 409)
    conflicting_payload = dict(raw_payload_retry)
    conflicting_payload["station_outcomes"] = [
        {
            "station_id": "STN-01",
            "allocated_energy_kwh": 999.0,  # Differing energy
            "available_capacity_kw": 500.0,
            "reported_unmet_demand_kwh": 0.0,
        }
    ]
    with pytest.raises(IdempotencyConflictError) as exc_conflict:
        live_provider.submit_feedback(conflicting_payload)
    assert "conflict" in exc_conflict.value.message.lower()

    # -------------------------------------------------------------------------
    # STEP 5: Retrieve adjusted demand using originating forecast ID & predictor feedback ID
    # -------------------------------------------------------------------------
    target_start_2 = base_start + timedelta(hours=1)
    target_end_2 = target_start_2 + timedelta(hours=1)
    adj_data = live_provider.get_next_operational_adjustment(
        feedback_id=predictor_feedback_id,
        target_interval_start=target_start_2.isoformat(),
        target_interval_end=target_end_2.isoformat(),
        forecast_id=forecast_id,
    )
    assert adj_data is not None
    assert len(adj_data["station_adjustments"]) == 3
    # Check that kWh is separate from vehicle counts
    stn1_adj = next(a for a in adj_data["station_adjustments"] if a["station_id"] == "STN-01")
    assert stn1_adj["original_predicted_arrivals"] == 6.0
    assert stn1_adj["adjusted_predicted_energy_kwh"] == 105.0

    # -------------------------------------------------------------------------
    # STEP 6: Subsequent allocation for Interval 2 using operational adjustment
    # -------------------------------------------------------------------------
    interval_2_req = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id=forecast_id,
        interval_start=target_start_2,
        interval_end=target_end_2,
        operational_adjustment_id=fb_res.operational_adjustment_id,
    )
    alloc_2 = alloc_service.run_allocation(interval_2_req)
    assert alloc_2.status == "success"
    assert alloc_2.constraint_validation_passed is True
    assert alloc_2.operational_adjustment_id == fb_res.operational_adjustment_id

    # Verify adjusted demand was used for STN-01 in Interval 2
    res_stn1 = next(r for r in alloc_2.results if r.station_id == "STN-01")
    assert res_stn1.predicted_energy_kwh == 105.0

    # Compile structured end-to-end execution summary
    summary = {
        "forecast_id": forecast_id,
        "allocation_run_id_interval_1": alloc_1.allocation_id,
        "allocation_run_id_interval_2": alloc_2.allocation_id,
        "feedback_id_local": local_feedback_id,
        "feedback_id_predictor": predictor_feedback_id,
        "operational_adjustment_id": fb_res.operational_adjustment_id,
        "optimization_status": alloc_2.status,
        "constraints_satisfied": alloc_2.constraint_validation_passed,
        "adjusted_demand_results": {
            r.station_id: {
                "predicted_energy_kwh": r.predicted_energy_kwh,
                "allocated_power_kw": r.allocated_power_kw,
                "served_energy_kwh": r.estimated_served_energy_kwh,
                "unserved_energy_kwh": r.estimated_unserved_energy_kwh,
            }
            for r in alloc_2.results
        },
        "contract_compliance": {
            "step_1_authenticated_forecast_retrieval": True,
            "step_2_canonical_station_mapping": True,
            "step_3_interval_1_optimization": True,
            "step_4_feedback_submission_and_idempotency": True,
            "step_5_adjusted_demand_retrieval": True,
            "step_6_interval_2_adjusted_allocation": True,
        },
    }

    assert summary["constraints_satisfied"] is True
    assert summary["adjusted_demand_results"]["STN-01"]["predicted_energy_kwh"] == 105.0
    assert summary["contract_compliance"]["step_6_interval_2_adjusted_allocation"] is True
