import pytest
from datetime import datetime, timezone


def test_create_baseline_forecast_mock(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-02"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 201
    ack = resp.json()

    assert ack["contract_version"] == "1.0"
    assert ack["status"] == "generated"
    assert ack["demand_type"] == "baseline"
    assert ack["scenario_id"] == "SCN-TEST-01"
    assert ack["interval_minutes"] == 60
    assert ack["horizon_intervals"] == 6
    assert "forecast_id" in ack
    assert ack["forecast_url"] == f"/api/v1/forecasts/{ack['forecast_id']}"

    # Verify retrieval of the created forecast
    get_resp = client.get(f"/api/v1/forecasts/{ack['forecast_id']}")
    assert get_resp.status_code == 200
    forecast_data = get_resp.json()
    assert forecast_data["forecast_id"] == ack["forecast_id"]
    # 6 intervals * 2 stations = 12 intervals
    assert len(forecast_data["intervals"]) == 12


def test_create_baseline_forecast_unaligned_start_rejected(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01"],
        "forecast_start": "2026-10-26T08:15:00Z",  # Not hour-aligned
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 422
    assert "aligned to the top of the hour" in resp.text


def test_create_baseline_forecast_duplicate_stations_rejected(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01", "STN-01"],  # Duplicate
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 422
    assert "duplicate" in resp.text


def test_create_baseline_forecast_empty_stations_rejected(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": [],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 422


def test_create_baseline_forecast_unsupported_interval_rejected(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 30,  # Unsupported interval (not 60)
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 422
    assert "Unsupported interval_minutes: 30" in resp.text


def test_create_baseline_forecast_unsupported_horizon_rejected(client):
    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 12,  # Unsupported horizon (not 6)
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 422
    assert "Unsupported horizon_intervals: 12" in resp.text


def test_baseline_snapshot_immutability_conflict_rejected(client, db_session):
    from app.repositories.forecast_snapshot_repo import ForecastSnapshotRepository
    from app.schemas.forecast import ForecastIntervalItem
    from app.core.exceptions import InvalidForecastError
    from datetime import timedelta

    payload = {
        "scenario_id": "SCN-TEST-01",
        "station_ids": ["STN-01"],
        "forecast_start": "2026-10-26T08:00:00Z",
        "interval_minutes": 60,
        "horizon_intervals": 6,
    }
    resp = client.post("/api/v1/forecasts", json=payload)
    assert resp.status_code == 201
    ack = resp.json()
    forecast_id = ack["forecast_id"]

    repo = ForecastSnapshotRepository(db_session)
    existing = repo.get_by_forecast_id(forecast_id)
    assert len(existing) == 6

    # Attempting to save conflicting items with differing arrivals for the same forecast_id
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    conflicting_items = [
        ForecastIntervalItem(
            forecast_id=forecast_id,
            scenario_id="SCN-TEST-01",
            station_id="STN-01",
            interval_start=base_start + timedelta(hours=i),
            interval_end=base_start + timedelta(hours=i + 1),
            interval_minutes=60,
            predicted_arrivals=999.0,  # Conflicting value
            predicted_energy_kwh=9999.0,
            model_version="mock-v1.0",
            generated_at=base_start,
        )
        for i in range(6)
    ]

    with pytest.raises(InvalidForecastError) as exc_info:
        repo.save_snapshot("SNAP-CONFLICT", conflicting_items)
    assert "Conflicting snapshot content rejected" in exc_info.value.message
