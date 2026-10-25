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
    assert repeat_resp.json()["operational_adjustment_id"] == fb_data["operational_adjustment_id"]


def test_failed_feedback_retry_succeeds(client, db_session):
    from app.models.feedback import FeedbackRecord
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

    idemp_key = f"TEST-FAIL-RETRY-{alloc_id}"
    # 2. First submission succeeds initially
    fb_req = {"deferred_fraction": 0.70, "idempotency_key": idemp_key}
    fb_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert fb_resp.status_code == 201
    fb_id = fb_resp.json()["feedback_id"]

    # 3. Simulate failure state in DB for testing retry mechanism
    fb_record = db_session.query(FeedbackRecord).filter(FeedbackRecord.feedback_id == fb_id).first()
    fb_record.submission_status = "failed"
    fb_record.error_details = "Simulated upstream timeout"
    fb_record.retry_count = 0
    db_session.commit()

    # Verify simulated failed state
    check_resp = client.get(f"/api/v1/feedback/{fb_id}")
    assert check_resp.json()["submission_status"] == "failed"

    # 4. Retry submission with the SAME idempotency key
    retry_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert retry_resp.status_code == 201
    retry_data = retry_resp.json()

    # Must be the same feedback_id, but status now updated to submitted, retry_count incremented
    assert retry_data["feedback_id"] == fb_id
    assert retry_data["submission_status"] == "submitted"
    assert retry_data["retry_count"] == 1
    assert retry_data["error_details"] is None
    assert retry_data["operational_adjustment_id"] is not None

    # 5. Subsequent idempotent call maintains submitted state and does not increment retry_count
    cached_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
    assert cached_resp.status_code == 201
    assert cached_resp.json()["submission_status"] == "submitted"
    assert cached_resp.json()["retry_count"] == 1
