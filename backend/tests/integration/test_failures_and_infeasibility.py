def test_unknown_forecast_id_returns_404(client):
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-NOTFOUND",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    resp = client.post("/api/v1/allocations/run", json=req)
    assert resp.status_code == 404


def test_invalid_forecast_schema_returns_422(client):
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-INVALID",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    resp = client.post("/api/v1/allocations/run", json=req)
    assert resp.status_code == 422


def test_unknown_scenario_returns_404(client):
    req = {
        "scenario_id": "SCN-NONEXISTENT",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    resp = client.post("/api/v1/allocations/run", json=req)
    assert resp.status_code == 404


def test_infeasible_grid_reported_safely(client):
    # Set grid limit to an extremely low number or other_load higher than limit
    # Update grid group GRID-METRO other_load to exceed limit
    update_payload = {"other_load_kw": 650.0}  # limit is 600, residual is 0
    resp = client.put("/api/v1/grid-groups/GRID-METRO", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["residual_capacity_kw"] == 0.0

    # Running allocation with 0 residual capacity must handle gracefully
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    alloc_resp = client.post("/api/v1/allocations/run", json=req)
    assert alloc_resp.status_code == 201
    data = alloc_resp.json()
    # When residual grid power is 0, allocated power must be 0
    for r in data["results"]:
        assert r["allocated_power_kw"] == 0.0
        assert r["estimated_served"] == 0.0
        assert r["estimated_unserved"] == r["predicted_arrivals"]
