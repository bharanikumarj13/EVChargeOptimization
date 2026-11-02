import pytest
from datetime import datetime, timezone
from app.core.config import settings
from app.core.exceptions import ProviderIntegrationError
from app.services.allocation_service import AllocationService
from app.services.feedback_service import FeedbackService
from app.schemas.allocation import AllocationRunRequest
from app.schemas.feedback import FeedbackCreateRequest
from app.integrations.live_provider import LiveForecastProvider


def test_health_endpoints_remain_public(client):
    """Liveness probe /healthz and partner probe /api/v1/integration/health must be public."""
    res1 = client.get("/healthz")
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    res2 = client.get("/api/v1/integration/health")
    assert res2.status_code == 200
    assert res2.json()["status"] == "healthy"


def test_inbound_auth_valid_service_token(client, monkeypatch):
    """Server-to-server request from EVCharge-Predict with valid OPT_SERVICE_TOKEN succeeds."""
    test_token = "predict-to-opt-secret-token-12345"
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", test_token)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {"Authorization": f"Bearer {test_token}"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_inbound_auth_invalid_service_token_returns_403(client, monkeypatch):
    """Server-to-server request with wrong token returns HTTP 403 Forbidden."""
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "valid-token-secret")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {"Authorization": "Bearer wrong-or-forged-token"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 403
    assert "Invalid or expired partner service authorization token" in res.json()["detail"]


def test_inbound_auth_missing_token_production_returns_401(client, monkeypatch):
    """Direct request without Bearer token in production returns HTTP 401."""
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "valid-token-secret")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    res = client.get("/api/v1/stations")
    assert res.status_code == 401
    assert "Missing Authorization header or Bearer token" in res.json()["detail"]


def test_spoofed_origin_header_rejected_in_production_401(client, monkeypatch):
    """
    SECURITY TEST: An attacker sending an 'Origin' or 'Referer' header matching CORS_ORIGINS
    must NEVER bypass authentication. Origin is a browser security mechanism, not an identity check.
    """
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "valid-token-secret")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://evcharge-opt.onrender.com")

    # Attacker attempts to spoof origin header without token
    headers = {"Origin": "https://evcharge-opt.onrender.com"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 401
    assert "Missing Authorization header or Bearer token" in res.json()["detail"]

    # Attacker attempts with Referer header
    headers = {"Referer": "https://evcharge-opt.onrender.com/overview"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 401


def test_inbound_auth_valid_browser_client_token(client, monkeypatch):
    """Browser request carrying a valid OPT_CLIENT_TOKEN in Authorization header succeeds."""
    client_token = "client-browser-token-xyz789"
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "server-service-token-123")
    monkeypatch.setattr(settings, "OPT_CLIENT_TOKEN", client_token)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {"Authorization": f"Bearer {client_token}"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 200


def test_inbound_auth_valid_client_token_header(client, monkeypatch):
    """Browser/client request carrying valid X-Client-Token header succeeds."""
    client_token = "client-header-token-abc456"
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "server-service-token-123")
    monkeypatch.setattr(settings, "OPT_CLIENT_TOKEN", client_token)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {"X-Client-Token": client_token}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 200


def test_inbound_auth_invalid_browser_client_token_returns_403(client, monkeypatch):
    """Browser request with an invalid client token returns HTTP 403 Forbidden."""
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "server-service-token-123")
    monkeypatch.setattr(settings, "OPT_CLIENT_TOKEN", "correct-client-token")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {"Authorization": "Bearer bad-client-token"}
    res = client.get("/api/v1/stations", headers=headers)
    assert res.status_code == 403
    assert "Invalid or expired partner service authorization token" in res.json()["detail"]


def test_cors_preflight_options_request_bypasses_auth(client, monkeypatch):
    """CORS preflight OPTIONS requests must succeed without authentication to allow browser preflight."""
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", "server-service-token-123")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    headers = {
        "Origin": "http://127.0.0.1:5174",
        "Access-Control-Request-Method": "GET",
    }
    res = client.options("/api/v1/stations", headers=headers)
    # CORS preflight OPTIONS requests are answered by CORS middleware with 200 OK
    assert res.status_code == 200


def test_missing_production_config_fails_closed_503(client, monkeypatch):
    """
    When APP_ENV == 'production' and OPT_SERVICE_TOKEN is unconfigured,
    the application fails closed with HTTP 503 instead of exposing unauthenticated endpoints.
    """
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", None)
    monkeypatch.setattr(settings, "OPT_CLIENT_TOKEN", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")

    res = client.get("/api/v1/stations")
    assert res.status_code == 503
    assert "Service authentication token is not configured in production environment" in res.json()["detail"]


def test_inbound_auth_sandbox_mode_open_when_token_unset(client, monkeypatch):
    """When OPT_SERVICE_TOKEN is unset in development/mock sandbox, open access is allowed."""
    monkeypatch.setattr(settings, "OPT_SERVICE_TOKEN", None)
    monkeypatch.setattr(settings, "OPT_CLIENT_TOKEN", None)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "ENFORCE_INBOUND_AUTH", False)

    res = client.get("/api/v1/stations")
    assert res.status_code == 200


def test_feedback_outcome_station_capacity_before_allocation(db_session):
    """
    TASK 3 VERIFICATION:
    Verifies that StationFeedbackOutcome strictly distinguishes:
    - allocated_energy_kwh (kWh energy served)
    - available_capacity_kw (Station operational capacity before allocation in kW:
      min(station_power_limit_kw, available_chargers * charger_power_kw_per_charger))
    - reported_unmet_demand_kwh (kWh energy unmet)
    - allocated_power_kw (Active power delivered by optimizer in kW)

    Confirms available_capacity_kw does NOT blindly equal allocated_power_kw.
    """
    from app.repositories.station_repo import StationRepository
    alloc_service = AllocationService(db_session)
    feedback_service = FeedbackService(db_session)
    station_repo = StationRepository(db_session)

    # Fetch STN-01 specs: 8 chargers * 50 kW = 400 kW, power limit 350 kW -> station capacity = 350 kW
    stn_01 = station_repo.get_by_id("STN-01")
    assert stn_01 is not None
    expected_stn_01_capacity = min(
        float(stn_01.station_power_limit_kw),
        float(stn_01.available_chargers * stn_01.charger_power_kw_per_charger),
    )
    assert expected_stn_01_capacity == 350.0

    req = AllocationRunRequest(
        scenario_id="SCN-TEST-01",
        forecast_id="FC-001",
        interval_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_end=datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc),
        operational_adjustment_id=None,
    )
    alloc_res = alloc_service.run_allocation(req)
    assert alloc_res.status == "success"

    fb = feedback_service.submit_allocation_feedback(
        alloc_res.allocation_id,
        FeedbackCreateRequest(deferred_fraction=0.70, idempotency_key=f"TEST-UNITS-{alloc_res.allocation_id}"),
    )
    assert fb.submission_status == "submitted"
    assert len(fb.station_outcomes) > 0

    stn_01_outcome = next(o for o in fb.station_outcomes if o.station_id == "STN-01")
    # Station available capacity before allocation is 350.0 kW
    assert stn_01_outcome.available_capacity_kw == 350.0

    # Allocated power is optimizer dispatch: 235.4 kW
    assert stn_01_outcome.allocated_power_kw == 235.4

    # Allocated energy is served energy: 235.4 kWh
    assert stn_01_outcome.allocated_energy_kwh == 235.4

    # Reported unmet demand is 0.0 kWh
    assert stn_01_outcome.reported_unmet_demand_kwh == 0.0

    # CRITICAL INVARIANT: available_capacity_kw != allocated_power_kw when allocated < station capacity
    assert stn_01_outcome.available_capacity_kw != stn_01_outcome.allocated_power_kw


def test_live_provider_handles_auth_failures_401_403(monkeypatch):
    """Verifies that live provider detects and propagates HTTP 401/403 as non-retryable ProviderIntegrationError."""
    import httpx
    provider = LiveForecastProvider(
        base_url="https://mock-predict-service.local",
        service_token="test-token",
    )

    class Mock401Response:
        status_code = 401
        text = "Unauthorized: Invalid or expired Bearer token"

        def json(self):
            return {"detail": self.text}

    class Mock403Response:
        status_code = 403
        text = "Forbidden: Insufficient token scope"

        def json(self):
            return {"detail": self.text}

    # Test get_forecast with 401
    monkeypatch.setattr(httpx.Client, "get", lambda *args, **kwargs: Mock401Response())
    with pytest.raises(ProviderIntegrationError) as exc401:
        provider.get_forecast("fcst_test_401")
    assert exc401.value.is_retryable is False
    assert "authentication failure" in exc401.value.message

    # Test get_forecast with 403
    monkeypatch.setattr(httpx.Client, "get", lambda *args, **kwargs: Mock403Response())
    with pytest.raises(ProviderIntegrationError) as exc403:
        provider.get_forecast("fcst_test_403")
    assert exc403.value.is_retryable is False
    assert "authentication failure" in exc403.value.message
