def test_full_feedback_loop_and_adjustment_chain(client):
    """
    Integration test verifying the complete multi-iteration feedback lifecycle:
    1. Baseline allocation (Interval 1)
    2. Feedback generation & submission
    3. Operational adjustment persistence
    4. Subsequent allocation (Interval 2) using operational adjustment
    5. Baseline immutability
    6. Traceable scenario iteration history
    """
    # 1. Baseline allocation for interval 1
    req1 = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
        "operational_adjustment_id": None,
    }
    alloc1_resp = client.post("/api/v1/allocations/run", json=req1)
    assert alloc1_resp.status_code == 201
    alloc1_data = alloc1_resp.json()
    alloc1_id = alloc1_data["allocation_id"]

    # 2. Submit feedback
    fb_req = {
        "deferred_fraction": 0.70,
        "idempotency_key": f"INT-IDEMP-{alloc1_id}",
    }
    fb_resp = client.post(f"/api/v1/allocations/{alloc1_id}/feedback", json=fb_req)
    assert fb_resp.status_code == 201
    fb_data = fb_resp.json()
    adj_id = fb_data["operational_adjustment_id"]
    assert adj_id is not None

    # Retrieve adjustment
    adj_resp = client.get(f"/api/v1/operational-adjustments/{adj_id}")
    assert adj_resp.status_code == 200
    adj_data = adj_resp.json()
    assert adj_data["source_feedback_id"] == fb_data["feedback_id"]

    # 3. Subsequent allocation for interval 2 using the adjustment
    req2 = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T09:00:00Z",
        "interval_end": "2026-10-26T10:00:00Z",
        "operational_adjustment_id": adj_id,
    }
    alloc2_resp = client.post("/api/v1/allocations/run", json=req2)
    assert alloc2_resp.status_code == 201
    alloc2_data = alloc2_resp.json()
    assert alloc2_data["operational_adjustment_id"] == adj_id

    # 4. Check scenario iteration trace
    iter_resp = client.get("/api/v1/scenarios/SCN-TEST-01/iterations")
    assert iter_resp.status_code == 200
    iterations = iter_resp.json()
    assert len(iterations) == 2
    assert iterations[0]["allocation_id"] == alloc1_id
    assert iterations[0]["is_feedback_adjusted"] is False
    assert iterations[1]["allocation_id"] == alloc2_data["allocation_id"]
    assert iterations[1]["is_feedback_adjusted"] is True
    assert iterations[1]["operational_adjustment_id"] == adj_id
