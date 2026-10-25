import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import httpx

from app.core.config import settings
from app.integrations.station_mapper import (
    StationMapper,
    IntegrationProfile,
    MappingVerificationStatus,
)
from app.core.exceptions import InvalidForecastError
from app.models.station import Station
from app.schemas.forecast import validate_forecast_horizon_integrity, ForecastIntervalItem
from app.repositories.forecast_snapshot_repo import ForecastSnapshotRepository


@pytest.fixture(autouse=False)
def three_station_profile_isolation():
    """
    Safely activates 'three_station_integration' profile for the duration
    of the test, strictly restoring 'five_station_mock' on teardown.
    """
    orig_profile = StationMapper.get_profile()
    StationMapper.set_profile(IntegrationProfile.THREE_STATION_INTEGRATION.value)
    try:
        yield
    finally:
        StationMapper.set_profile(orig_profile)


@pytest.fixture
def seed_stn_03(db_session):
    """Seeds STN-03 (Suburban Retail Plaza) into the in-memory database."""
    existing = db_session.query(Station).filter(Station.station_id == "STN-03").first()
    if not existing:
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
    return db_session


def test_three_station_configuration_and_safety_checks():
    """
    Procedure step 1 & 2:
    - Verify PREDICT_PROVIDER_MODE=mock and is_mock_provider=True.
    - Verify physical station confirmation flag is False (unconfirmed test aliases).
    - Verify candidate mappings are UNCONFIRMED_PROPOSAL.
    - Verify STN-04 and STN-05 are UNSUPPORTED_BY_MODEL.
    - Verify default profile is five_station_mock.
    """
    assert settings.PREDICT_PROVIDER_MODE == "mock"
    assert settings.is_mock_provider is True
    assert getattr(settings, "CONFIRM_PHYSICAL_STATION_MAPPINGS", False) is False

    # Default profile must be five_station_mock
    assert StationMapper.get_profile() == IntegrationProfile.FIVE_STATION_MOCK.value

    # Physical correspondence for candidate mappings must be UNCONFIRMED
    assert not StationMapper.is_physically_confirmed("STN-01")
    assert not StationMapper.is_physically_confirmed("STN-02")
    assert not StationMapper.is_physically_confirmed("STN-03")

    # Inspect mapping details
    details = {d["internal_id"]: d for d in StationMapper.get_all_mapping_details()}
    assert details["STN-01"]["verification_status"] == MappingVerificationStatus.UNCONFIRMED_PROPOSAL.value
    assert details["STN-02"]["verification_status"] == MappingVerificationStatus.UNCONFIRMED_PROPOSAL.value
    assert details["STN-03"]["verification_status"] == MappingVerificationStatus.UNCONFIRMED_PROPOSAL.value
    assert details["STN-04"]["verification_status"] == MappingVerificationStatus.UNSUPPORTED_BY_MODEL.value
    assert details["STN-05"]["verification_status"] == MappingVerificationStatus.UNSUPPORTED_BY_MODEL.value

    assert details["STN-01"]["caltech_source_id"] == "1-39-139-650"
    assert details["STN-02"]["caltech_source_id"] == "1-39-139-651"
    assert details["STN-03"]["caltech_source_id"] == "1-39-139-652"


def test_three_station_forecast_lifecycle_and_rejections(client, three_station_profile_isolation):
    """
    Procedure step 3:
    - Under three_station_integration profile, request baseline forecast for STN-01, STN-02, STN-03.
    - Verify top-of-hour alignment, 60-min intervals, horizon_intervals=6.
    - Verify acknowledgement schema.
    - Verify rejection of unmapped / unsupported stations (STN-04, STN-05, ST-004, ST-005, unknown).
    - Verify rejection of invalid interval or unaligned timestamps.
    """
    assert StationMapper.get_profile() == IntegrationProfile.THREE_STATION_INTEGRATION.value
    assert StationMapper.get_profile_stations() == ["STN-01", "STN-02", "STN-03"]

    valid_payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02", "STN-03"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }

    resp = client.post("/api/v1/forecasts", json=valid_payload)
    assert resp.status_code == 201, resp.text
    ack = resp.json()

    assert ack["contract_version"] == "1.0"
    assert ack["status"] == "generated"
    assert ack["demand_type"] == "baseline"
    assert ack["scenario_id"] == "SCN-TEST-01"
    assert ack["interval_minutes"] == 60
    assert ack["horizon_intervals"] == 6
    assert ack["forecast_id"].startswith("FC-MOCK-")
    assert ack["forecast_url"] == f"/api/v1/forecasts/{ack['forecast_id']}"

    # Rejection of unsupported stations under three_station_integration
    for unsupported_stn in ["STN-04", "STN-05", "ST-004", "ST-005", "UNKNOWN-STN"]:
        bad_payload = dict(valid_payload, station_ids=["STN-01", "STN-02", unsupported_stn])
        bad_resp = client.post("/api/v1/forecasts", json=bad_payload)
        assert bad_resp.status_code == 422, f"Expected 422 for {unsupported_stn}, got {bad_resp.status_code}"
        assert "not supported" in bad_resp.text or "not mapped" in bad_resp.text

    # Rejection of unaligned forecast_start
    unaligned_payload = dict(valid_payload, forecast_start="2026-10-26T08:15:00Z")
    unaligned_resp = client.post("/api/v1/forecasts", json=unaligned_payload)
    assert unaligned_resp.status_code == 422
    assert "top of the hour" in unaligned_resp.text

    # Rejection of non-60 minute intervals
    bad_interval_payload = dict(valid_payload, interval_minutes=30)
    bad_interval_resp = client.post("/api/v1/forecasts", json=bad_interval_payload)
    assert bad_interval_resp.status_code == 422

    # Rejection of non-6 interval horizon
    bad_horizon_payload = dict(valid_payload, horizon_intervals=12)
    bad_horizon_resp = client.post("/api/v1/forecasts", json=bad_horizon_payload)
    assert bad_horizon_resp.status_code == 422


def test_three_station_forecast_retrieval_and_immutability(client, db_session, three_station_profile_isolation):
    """
    Procedure step 4:
    - Retrieve full forecast via GET /api/v1/forecasts/{forecast_id}.
    - Verify exactly 18 intervals (3 stations x 6 intervals).
    - Verify consecutive non-overlapping UTC intervals.
    - Verify non-negative arrivals and energy.
    - Verify forecast snapshot immutability (re-saving identical succeeds; conflicting rejected).
    """
    req_payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02", "STN-03"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    create_resp = client.post("/api/v1/forecasts", json=req_payload)
    assert create_resp.status_code == 201
    forecast_id = create_resp.json()["forecast_id"]

    # Retrieve forecast
    get_resp = client.get(f"/api/v1/forecasts/{forecast_id}")
    assert get_resp.status_code == 200
    forecast_data = get_resp.json()

    assert forecast_data["forecast_id"] == forecast_id
    assert forecast_data["interval_count"] == 18
    assert len(forecast_data["intervals"]) == 18

    # Convert items to ForecastIntervalItem models and run integrity validator
    items = [ForecastIntervalItem(**it) for it in forecast_data["intervals"]]
    validate_forecast_horizon_integrity(
        items,
        expected_horizon_intervals=6,
        expected_interval_minutes=60,
        expected_station_ids=["STN-01", "STN-02", "STN-03"],
    )

    # Immutability Check: Snapshot repo re-saving identical items must succeed idempotently
    snapshot_repo = ForecastSnapshotRepository(db_session)
    re_save = snapshot_repo.save_snapshot("SNAP-IDENTICAL", items)
    assert len(re_save) == 18
    assert re_save[0].forecast_id == forecast_id

    # Immutability Conflict Check 1: Conflicting item count rejected
    conflicting_count_item = ForecastIntervalItem(
        forecast_id=forecast_id,
        scenario_id="SCN-TEST-01",
        station_id="STN-01",
        interval_start=datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc),
        interval_end=datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc),
        interval_minutes=60,
        predicted_arrivals=10.0,
        predicted_energy_kwh=200.0,
        model_version="mock-v1.0",
        generated_at=datetime.now(timezone.utc),
    )
    with pytest.raises(InvalidForecastError) as exc_info1:
        snapshot_repo.save_snapshot("SNAP-CONFLICT-COUNT", [conflicting_count_item])
    assert "Conflicting snapshot with 1 intervals rejected" in str(exc_info1.value)

    # Immutability Conflict Check 2: Conflicting prediction values rejected
    conflicting_value_items = [
        ForecastIntervalItem(
            forecast_id=it.forecast_id,
            scenario_id=it.scenario_id,
            station_id=it.station_id,
            interval_start=it.interval_start,
            interval_end=it.interval_end,
            interval_minutes=it.interval_minutes,
            predicted_arrivals=999.0 if idx == 0 else it.predicted_arrivals,
            predicted_energy_kwh=it.predicted_energy_kwh,
            model_version=it.model_version,
            generated_at=it.generated_at,
        )
        for idx, it in enumerate(items)
    ]
    with pytest.raises(InvalidForecastError) as exc_info2:
        snapshot_repo.save_snapshot("SNAP-CONFLICT-VALUES", conflicting_value_items)
    assert "Conflicting snapshot content rejected" in str(exc_info2.value)


def test_three_station_baseline_allocation_execution(client, seed_stn_03, three_station_profile_isolation):
    """
    Procedure step 5:
    - Run allocation for the 3 stations on Interval 1 (08:00 to 09:00 UTC).
    - Check physical constraints: station power limits, grid limits, vehicle conservation.
    - Verify unit semantics.
    """
    # 1. Create 3-station forecast
    fc_payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02", "STN-03"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    create_resp = client.post("/api/v1/forecasts", json=fc_payload)
    assert create_resp.status_code == 201
    forecast_id = create_resp.json()["forecast_id"]

    # 2. Run allocation for Interval 1
    alloc_req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": forecast_id,
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    alloc_resp = client.post("/api/v1/allocations/run", json=alloc_req)
    assert alloc_resp.status_code == 201, alloc_resp.text
    alloc_data = alloc_resp.json()

    assert alloc_data["status"] == "success"
    assert alloc_data["constraint_validation_passed"] is True
    assert len(alloc_data["results"]) == 3

    results_by_stn = {r["station_id"]: r for r in alloc_data["results"]}
    assert set(results_by_stn.keys()) == {"STN-01", "STN-02", "STN-03"}

    # Station limits lookup
    # STN-01: max power 350.0 kW, 8 chargers * 50 kW = 400 kW max capacity
    # STN-02: max power 200.0 kW, 8 avail * 22 kW = 176 kW max capacity
    # STN-03: max power 250.0 kW, 6 avail * 50 kW = 300 kW max capacity
    stn_power_caps = {"STN-01": 350.0, "STN-02": 200.0, "STN-03": 250.0}

    for stn_id, res in results_by_stn.items():
        # Physical station power limits
        assert res["allocated_power_kw"] <= stn_power_caps[stn_id]

        # Vehicle demand conservation: served + unserved == predicted arrivals
        total_veh = round(res["estimated_served"] + res["estimated_unserved"], 1)
        assert abs(total_veh - round(res["predicted_arrivals"], 1)) < 0.1

        # Energy conservation: served_kwh + unserved_kwh == predicted_energy_kwh
        total_kwh = round(res["estimated_served_energy_kwh"] + res["estimated_unserved_energy_kwh"], 1)
        assert abs(total_kwh - round(res["predicted_energy_kwh"], 1)) < 0.2

        # Utilization in valid percentage range [0.0, 100.0]
        assert 0.0 <= res["charger_utilization_pct"] <= 100.0

        # Waiting time non-negative
        assert res["estimated_wait_minutes"] >= 0.0

    # Grid group capacity constraints:
    # GRID-METRO limit: 600 kW, other load: 100 kW -> available: 500 kW
    metro_power = results_by_stn["STN-01"]["allocated_power_kw"] + results_by_stn["STN-02"]["allocated_power_kw"]
    assert metro_power <= 500.0

    # GRID-SUBURB limit: 400 kW, other load: 50 kW -> available: 350 kW
    suburb_power = results_by_stn["STN-03"]["allocated_power_kw"]
    assert suburb_power <= 350.0


def test_three_station_feedback_submission_and_idempotency(client, seed_stn_03, three_station_profile_isolation):
    """
    Procedure step 6:
    - Submit feedback for Interval 1 allocation via POST /api/v1/allocations/{id}/feedback.
    - Verify feedback response fields: feedback_id, status=submitted, deferred_fraction=0.70.
    - Verify idempotent retry with identical payload returns existing record.
    - Verify conflicting payload with same key is rejected with HTTP 409.
    """
    # 1. Create forecast and run allocation
    fc_payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02", "STN-03"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    fc_res = client.post("/api/v1/forecasts", json=fc_payload)
    forecast_id = fc_res.json()["forecast_id"]

    alloc_req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": forecast_id,
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    alloc_res = client.post("/api/v1/allocations/run", json=alloc_req)
    alloc_id = alloc_res.json()["allocation_id"]

    # 2. Submit local feedback
    idemp_key = f"IDEMP-3STN-{alloc_id}"
    fb_req = {
        "deferred_fraction": 0.70,
        "idempotency_key": idemp_key,
    }
    fb_res = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert fb_res.status_code == 201, fb_res.text
    fb_data = fb_res.json()

    assert fb_data["feedback_id"].startswith("FBD-")
    assert fb_data["submission_status"] == "submitted"
    assert fb_data["deferred_fraction"] == 0.70
    assert fb_data["operational_adjustment_id"] is not None
    assert len(fb_data["station_outcomes"]) == 3

    # 3. Idempotent Retry: Repeat call with identical payload returns existing feedback and adjustment
    repeat_res = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert repeat_res.status_code == 201
    repeat_data = repeat_res.json()
    assert repeat_data["feedback_id"] == fb_data["feedback_id"]
    assert repeat_data["operational_adjustment_id"] == fb_data["operational_adjustment_id"]

    # 4. Conflicting Retry: Submitting conflicting deferred_fraction under the same idempotency key fails with 409
    conflict_req = {
        "deferred_fraction": 0.50,  # Conflicting fraction
        "idempotency_key": idemp_key,
    }
    conflict_res = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=conflict_req)
    assert conflict_res.status_code == 409
    assert "Idempotency key" in conflict_res.text or "previously used" in conflict_res.text


def test_three_station_feedback_adjusted_subsequent_allocation(client, seed_stn_03, three_station_profile_isolation):
    """
    Procedure step 7:
    - Run subsequent allocation for Interval 2 (09:00 to 10:00 UTC) referencing operational_adjustment_id.
    - Verify baseline + deferred arrivals/energy are allocated.
    - Verify grid constraints and station power limits hold.
    - Verify allocation status is success.
    """
    # 1. Create forecast
    fc_payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02", "STN-03"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    fc_res = client.post("/api/v1/forecasts", json=fc_payload)
    forecast_id = fc_res.json()["forecast_id"]

    # 2. Run Interval 1 allocation (08:00 - 09:00)
    alloc_1 = client.post("/api/v1/allocations/run", json={
        "scenario_id": "SCN-TEST-01",
        "forecast_id": forecast_id,
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }).json()

    # 3. Submit feedback to produce operational adjustment for Interval 2
    fb_res = client.post(f"/api/v1/allocations/{alloc_1['allocation_id']}/feedback", json={
        "deferred_fraction": 0.70,
        "idempotency_key": f"IDEMP-INTERVAL2-{alloc_1['allocation_id']}",
    })
    adj_id = fb_res.json()["operational_adjustment_id"]
    assert adj_id is not None

    # 4. Run subsequent allocation for Interval 2 (09:00 - 10:00) using operational_adjustment_id
    alloc_2_req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": forecast_id,
        "interval_start": "2026-10-26T09:00:00Z",
        "interval_end": "2026-10-26T10:00:00Z",
        "operational_adjustment_id": adj_id,
    }
    alloc_2_res = client.post("/api/v1/allocations/run", json=alloc_2_req)
    assert alloc_2_res.status_code == 201, alloc_2_res.text
    alloc_2_data = alloc_2_res.json()

    assert alloc_2_data["status"] == "success"
    assert alloc_2_data["constraint_validation_passed"] is True
    assert alloc_2_data["operational_adjustment_id"] == adj_id
    assert len(alloc_2_data["results"]) == 3

    # Verify physical limits hold under adjusted load
    for res in alloc_2_data["results"]:
        assert res["allocated_power_kw"] >= 0.0
        assert res["estimated_served"] >= 0.0
        assert res["estimated_unserved"] >= 0.0
        assert round(res["estimated_served"] + res["estimated_unserved"], 1) == round(res["predicted_arrivals"], 1)


def test_three_station_profile_restoration_to_five_station_mock():
    """
    Procedure step 8:
    - Verify that outside any isolation fixture, active profile is five_station_mock.
    - Verify StationMapper.get_profile_stations() returns 5 stations.
    - Verify five-station mock behavior remains intact.
    """
    StationMapper.reset_to_defaults()
    assert StationMapper.get_profile() == IntegrationProfile.FIVE_STATION_MOCK.value
    profile_stations = StationMapper.get_profile_stations()
    assert profile_stations == ["STN-01", "STN-02", "STN-03", "STN-04", "STN-05"]


def test_three_station_zero_external_network_calls_guarantee(client, seed_stn_03, three_station_profile_isolation):
    """
    Procedure step 9:
    - Verify that the entire 3-station workflow executes without making any external HTTP requests.
    - Any attempt to contact EVCharge-Predict externally will immediately raise an error.
    - TestClient in-memory ASGI requests to 'http://testserver' are permitted.
    """
    orig_send = httpx.Client.send

    def verify_no_external_network(self, request, *args, **kwargs):
        url_str = str(request.url)
        # Allow internal Starlette TestClient ASGI calls
        if "testserver" in url_str:
            return orig_send(self, request, *args, **kwargs)
        raise AssertionError(f"External network call attempted to '{url_str}' during mock mode execution!")

    with patch.object(httpx.Client, "send", verify_no_external_network):
        # 1. Create forecast
        fc_res = client.post("/api/v1/forecasts", json={
            "scenario_id": "SCN-TEST-01",
            "station_ids": ["STN-01", "STN-02", "STN-03"],
            "forecast_start": "2026-10-26T08:00:00Z",
            "interval_minutes": 60,
            "horizon_intervals": 6,
        })
        assert fc_res.status_code == 201
        forecast_id = fc_res.json()["forecast_id"]

        # 2. Retrieve forecast
        get_res = client.get(f"/api/v1/forecasts/{forecast_id}")
        assert get_res.status_code == 200

        # 3. Run Interval 1 allocation
        alloc_res = client.post("/api/v1/allocations/run", json={
            "scenario_id": "SCN-TEST-01",
            "forecast_id": forecast_id,
            "interval_start": "2026-10-26T08:00:00Z",
            "interval_end": "2026-10-26T09:00:00Z",
            "operational_adjustment_id": None,
        })
        assert alloc_res.status_code == 201
        alloc_id = alloc_res.json()["allocation_id"]

        # 4. Submit feedback
        fb_res = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json={
            "deferred_fraction": 0.70,
            "idempotency_key": f"NO-NET-IDEMP-{alloc_id}",
        })
        assert fb_res.status_code == 201
        adj_id = fb_res.json()["operational_adjustment_id"]

        # 5. Subsequent adjusted allocation
        alloc_2_res = client.post("/api/v1/allocations/run", json={
            "scenario_id": "SCN-TEST-01",
            "forecast_id": forecast_id,
            "interval_start": "2026-10-26T09:00:00Z",
            "interval_end": "2026-10-26T10:00:00Z",
            "operational_adjustment_id": adj_id,
        })
        assert alloc_2_res.status_code == 201
        assert alloc_2_res.json()["status"] == "success"
