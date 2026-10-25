def test_reports_summary_and_csv_export(client):
    # Summary
    summary_resp = client.get("/api/v1/reports/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "total_stations" in summary
    assert "total_grid_limit_kw" in summary

    # Run an allocation so CSV has rows
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    client.post("/api/v1/allocations/run", json=req)

    # Export CSV
    csv_resp = client.get("/api/v1/reports/allocations.csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "Allocation ID" in csv_resp.text
    assert "STN-01" in csv_resp.text
