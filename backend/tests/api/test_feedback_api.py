def test_submit_feedback_and_retrieve(client):
    # 1. Run allocation
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    alloc_resp = client.post("/api/v1/allocations/run", json=req)
    assert alloc_resp.status_code == 201
    alloc_id = alloc_resp.json()["allocation_id"]

    # 2. Submit feedback
    fb_req = {
        "deferred_fraction": 0.70,
        "idempotency_key": f"TEST-IDEMP-{alloc_id}",
    }
    fb_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert fb_resp.status_code == 201
    fb_data = fb_resp.json()
    fb_id = fb_data["feedback_id"]
    assert fb_data["submission_status"] == "submitted"
    assert fb_data["operational_adjustment_id"] is not None

    # 3. Retrieve feedback
    get_fb = client.get(f"/api/v1/feedback/{fb_id}")
    assert get_fb.status_code == 200
    assert get_fb.json()["feedback_id"] == fb_id

    # 4. Verify Idempotency: Repeating post returns same feedback
    repeat_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert repeat_resp.status_code == 201
    assert repeat_resp.json()["feedback_id"] == fb_id
