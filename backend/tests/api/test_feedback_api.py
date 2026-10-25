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


def test_feedback_conflicting_payload_same_key_rejected_409(client):
    # 1. Run allocation
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_resp = client.post("/api/v1/allocations/run", json=req)
    assert alloc_resp.status_code == 201
    alloc_id = alloc_resp.json()["allocation_id"]

    idemp_key = f"TEST-CONFLICT-KEY-{alloc_id}"

    # 2. First submission
    fb_req_1 = {"deferred_fraction": 0.50, "idempotency_key": idemp_key}
    fb_resp_1 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req_1)
    assert fb_resp_1.status_code == 201

    # 3. Second submission with SAME key but DIFFERENT payload (different deferred_fraction)
    fb_req_2 = {"deferred_fraction": 0.90, "idempotency_key": idemp_key}
    fb_resp_2 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req_2)
    assert fb_resp_2.status_code == 409
    assert "previously used for a different request payload" in fb_resp_2.text


def test_feedback_different_key_same_allocation_rejected_409(client):
    # 1. Run allocation
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_resp = client.post("/api/v1/allocations/run", json=req)
    assert alloc_resp.status_code == 201
    alloc_id = alloc_resp.json()["allocation_id"]

    # 2. First submission with KEY-A
    fb_req_a = {"deferred_fraction": 0.70, "idempotency_key": f"KEY-A-{alloc_id}"}
    fb_resp_a = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req_a)
    assert fb_resp_a.status_code == 201

    # 3. Second submission for same allocation with KEY-B
    fb_req_b = {"deferred_fraction": 0.70, "idempotency_key": f"KEY-B-{alloc_id}"}
    fb_resp_b = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req_b)
    assert fb_resp_b.status_code == 409
    assert "Only one feedback submission is permitted per allocation run" in fb_resp_b.text


def test_feedback_same_key_different_allocation_rejected_409(client):
    # Run two different allocations
    req_1 = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_1 = client.post("/api/v1/allocations/run", json=req_1).json()["allocation_id"]

    req_2 = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T09:00:00Z",
        "interval_end": "2026-10-26T10:00:00Z",
    }
    alloc_2 = client.post("/api/v1/allocations/run", json=req_2).json()["allocation_id"]

    shared_key = f"REUSED-KEY-ACROSS-ALLOCATIONS-{alloc_1}"

    # First allocation gets the key
    resp_1 = client.post(f"/api/v1/allocations/{alloc_1}/feedback", json={"idempotency_key": shared_key})
    assert resp_1.status_code == 201

    # Second allocation attempts to reuse the same key
    resp_2 = client.post(f"/api/v1/allocations/{alloc_2}/feedback", json={"idempotency_key": shared_key})
    assert resp_2.status_code == 409
    assert "different request payload or allocation run" in resp_2.text


def test_repeated_feedback_failure_increments_retry_count(client, db_session):
    from app.models.feedback import FeedbackRecord
    from unittest.mock import patch
    from app.core.exceptions import ProviderIntegrationError

    # 1. Run allocation
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_id = client.post("/api/v1/allocations/run", json=req).json()["allocation_id"]

    idemp_key = f"TEST-REPEAT-FAIL-{alloc_id}"
    fb_req = {"deferred_fraction": 0.70, "idempotency_key": idemp_key}

    # Simulate provider failure on submission
    with patch("app.integrations.mock_provider.MockForecastProvider.submit_feedback") as mock_submit:
        mock_submit.side_effect = ProviderIntegrationError("Network timeout", is_retryable=True)
        resp1 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
        assert resp1.status_code == 201
        assert resp1.json()["submission_status"] == "failed"
        assert resp1.json()["retry_count"] == 0

        # Second attempt fails again
        resp2 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
        assert resp2.status_code == 201
        assert resp2.json()["submission_status"] == "failed"
        assert resp2.json()["retry_count"] == 1

        # Third attempt fails again
        resp3 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json=fb_req)
        assert resp3.status_code == 201
        assert resp3.json()["submission_status"] == "failed"
        assert resp3.json()["retry_count"] == 2


def test_idempotent_retry_does_not_create_duplicate_operational_adjustment(client, db_session):
    from app.models.operational_adjustment import OperationalAdjustment

    # Run allocation
    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_id = client.post("/api/v1/allocations/run", json=req).json()["allocation_id"]
    idemp_key = f"TEST-ADJ-IDEMP-{alloc_id}"

    # First submission
    resp1 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json={"idempotency_key": idemp_key})
    assert resp1.status_code == 201
    adj_id = resp1.json()["operational_adjustment_id"]
    assert adj_id is not None

    count_before = db_session.query(OperationalAdjustment).filter(OperationalAdjustment.operational_adjustment_id == adj_id).count()
    assert count_before == 1

    # Repeat submission 3 times
    for _ in range(3):
        resp_rep = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json={"idempotency_key": idemp_key})
        assert resp_rep.status_code == 201
        assert resp_rep.json()["operational_adjustment_id"] == adj_id

    # Count must remain exactly 1 (no duplicate operational adjustments created)
    count_after = db_session.query(OperationalAdjustment).filter(OperationalAdjustment.operational_adjustment_id == adj_id).count()
    assert count_after == 1


def test_conflicting_retry_preserves_original_successful_record(client, db_session):
    from app.models.feedback import FeedbackRecord

    req = {
        "scenario_id": "SCN-TEST-01",
        "forecast_id": "FC-001",
        "interval_start": "2026-10-26T08:00:00Z",
        "interval_end": "2026-10-26T09:00:00Z",
    }
    alloc_id = client.post("/api/v1/allocations/run", json=req).json()["allocation_id"]
    idemp_key = f"TEST-PRESERVE-{alloc_id}"

    # Initial successful submission
    resp1 = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json={"deferred_fraction": 0.70, "idempotency_key": idemp_key})
    assert resp1.status_code == 201
    original_fb_id = resp1.json()["feedback_id"]

    # Attempt conflicting submission
    conflict_resp = client.post(f"/api/v1/allocations/{alloc_id}/feedback", json={"deferred_fraction": 0.30, "idempotency_key": idemp_key})
    assert conflict_resp.status_code == 409

    # Verify original record is completely untouched in DB
    record = db_session.query(FeedbackRecord).filter(FeedbackRecord.feedback_id == original_fb_id).first()
    assert record is not None
    assert record.submission_status == "submitted"
    assert record.deferred_fraction == 0.70
    assert record.retry_count == 0
