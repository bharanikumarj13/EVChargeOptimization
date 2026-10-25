from datetime import datetime, timezone


def test_run_allocation_and_retrieve(client):
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    resp = client.post("/api/v1/allocations/run", json=req)
    assert resp.status_code == 201
    data = resp.json()
    alloc_id = data["allocation_id"]
    assert data["status"] == "success"
    assert data["constraint_validation_passed"] is True
    assert len(data["results"]) >= 2

    # Retrieve allocation by ID
    get_resp = client.get(f"/api/v1/allocations/{alloc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["allocation_id"] == alloc_id

    # List allocations for scenario
    list_resp = client.get("/api/v1/scenarios/SCN-TEST-01/allocations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


def test_run_allocation_out_of_horizon_timestamp_rejected(client):
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T22:00:00Z",  # Outside 08:00 - 14:00 horizon
        "interval_end": "2026-10-26T23:00:00Z",
        "operational_adjustment_id": None,
    }
    resp = client.post("/api/v1/allocations/run", json=req)
    assert resp.status_code == 422
    assert "outside the forecast horizon" in resp.json()["message"]


def test_run_allocation_all_six_intervals(client):
    # Verify every one of the 6 intervals executes cleanly
    for hour_offset in range(6):
        start_hour = 8 + hour_offset
        end_hour = start_hour + 1
        req = {
            "scenario_id": "SCN-TEST-01",
            "forecast_id": "FC-001",
            "interval_start": f"2026-10-26T{start_hour:02d}:00:00Z",
            "interval_end": f"2026-10-26T{end_hour:02d}:00:00Z",
            "operational_adjustment_id": None,
        }
        resp = client.post("/api/v1/allocations/run", json=req)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["results"]) >= 2
