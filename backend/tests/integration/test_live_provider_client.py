import pytest
from unittest.mock import patch
import httpx
from datetime import datetime, timezone
from app.integrations.live_provider import LiveForecastProvider
from app.core.exceptions import ProviderIntegrationError, EntityNotFoundError


def test_live_provider_get_forecast_success(monkeypatch):
    mock_payload = {
        "forecast_id": "FC-LIVE-01",
        "scenario_id": "SCN-01",
        "model_version": "v2.0-neural",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intervals": [
            {
                "forecast_id": "FC-LIVE-01",
                "scenario_id": "SCN-01",
                "station_id": "STN-01",
                "interval_start": "2026-10-26T08:00:00Z",
                "interval_end": "2026-10-26T09:00:00Z",
                "interval_minutes": 60,
                "predicted_arrivals": 12.0,
                "predicted_energy_kwh": 260.0,
                "model_version": "v2.0-neural",
                "generated_at": "2026-10-26T06:00:00Z",
            }
        ],
        "interval_count": 1,
        "station_ids": ["STN-01"],
    }

    def mock_get(self, url, **kwargs):
        headers = kwargs.get("headers", {})
        assert "Authorization" in headers
        assert "Bearer mock-token-123" == headers["Authorization"]
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token="mock-token-123",
    )
    result = provider.get_forecast("FC-LIVE-01")
    assert result.forecast_id == "FC-LIVE-01"
    assert result.intervals[0].predicted_arrivals == 12.0


def test_live_provider_handles_timeout(monkeypatch):
    def mock_get(self, url, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token="token",
    )
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.get_forecast("FC-TIMEOUT")
    assert exc_info.value.is_retryable is True


def test_live_provider_handles_404_not_found(monkeypatch):
    def mock_get(self, url, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token="token",
    )
    with pytest.raises(EntityNotFoundError):
        provider.get_forecast("FC-UNKNOWN")


def test_live_provider_create_forecast_success(monkeypatch):
    recorded_calls = []

    def mock_post(self, url, **kwargs):
        recorded_calls.append(("POST", url, kwargs.get("json")))
        ack_payload = {
            "contract_version": "1.0",
            "forecast_id": "FC-NEW-100",
            "scenario_id": "SCN-01",
            "status": "generated",
            "demand_type": "baseline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interval_minutes": 60,
            "horizon_intervals": 6,
            "forecast_url": "/api/v1/forecasts/FC-NEW-100",
        }
        return httpx.Response(201, json=ack_payload, request=httpx.Request("POST", url))

    def mock_get(self, url, **kwargs):
        recorded_calls.append(("GET", url, kwargs.get("params")))
        # Return 6 intervals for ST-001
        from datetime import timedelta
        base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            intervals.append({
                "forecast_id": "FC-NEW-100",
                "scenario_id": "SCN-01",
                "station_id": "ST-001",
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "interval_minutes": 60,
                "predicted_arrivals": 10.0 + i,
                "predicted_energy_kwh": 200.0 + i * 20,
                "model_version": "v1.0",
                "generated_at": (base_start - timedelta(hours=1)).isoformat(),
            })
        resp_payload = {
            "forecast_id": "FC-NEW-100",
            "scenario_id": "SCN-01",
            "model_version": "v1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "intervals": intervals,
            "interval_count": 6,
            "station_ids": ["ST-001"],
        }
        return httpx.Response(200, json=resp_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    monkeypatch.setattr(httpx.Client, "get", mock_get)

    from app.schemas.forecast import ForecastCreateRequest

    provider = LiveForecastProvider(base_url="http://127.0.0.1:8001")
    req = ForecastCreateRequest(
        scenario_id="SCN-01",
        station_ids=["STN-01"],  # internal ID should be mapped to ST-001
        forecast_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_minutes=60,
        horizon_intervals=6,
    )
    ack = provider.create_forecast(req)

    assert ack.forecast_id == "FC-NEW-100"
    assert ack.status == "generated"
    assert len(recorded_calls) == 2
    post_call = recorded_calls[0]
    assert post_call[0] == "POST"
    assert post_call[1] == "http://127.0.0.1:8001/api/v1/forecasts"
    assert post_call[2]["station_ids"] == ["ST-001"]  # verified mapped to external canonical!


def test_live_provider_adjusted_demand_url_and_params(monkeypatch):
    recorded_calls = []

    def mock_get(self, url, **kwargs):
        recorded_calls.append(("GET", url, kwargs.get("params")))
        return httpx.Response(200, json={"adjusted": True, "feedback_id": "FBD-123"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="http://127.0.0.1:8001")
    res = provider.get_next_operational_adjustment(
        feedback_id="FBD-123",
        target_interval_start="2026-10-26T09:00:00Z",
        target_interval_end="2026-10-26T10:00:00Z",
        forecast_id="FC-NEW-100",
    )

    assert res == {"adjusted": True, "feedback_id": "FBD-123"}
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call[1] == "http://127.0.0.1:8001/api/v1/forecasts/FC-NEW-100/adjusted-demand"
    assert call[2] == {"feedback_id": "FBD-123"}


def test_live_provider_submit_feedback_suspended_error():
    provider = LiveForecastProvider(base_url="http://127.0.0.1:8001")
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.submit_feedback({"feedback_id": "FBD-TEST"})
    assert "not yet confirmed" in exc_info.value.message
    assert exc_info.value.is_retryable is False


def test_live_provider_acknowledgement_status_completed_accepted(monkeypatch):
    def mock_post(self, url, **kwargs):
        ack_payload = {
            "contract_version": "1.0",
            "forecast_id": "FC-COMPL-01",
            "scenario_id": "SCN-01",
            "status": "completed",  # Partner documented status: 'completed'
            "demand_type": "baseline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interval_minutes": 60,
            "horizon_intervals": 6,
            "forecast_url": "/api/v1/forecasts/FC-COMPL-01",
        }
        return httpx.Response(200, json=ack_payload, request=httpx.Request("POST", url))

    def mock_get(self, url, **kwargs):
        from datetime import timedelta
        base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            intervals.append({
                "forecast_id": "FC-COMPL-01",
                "scenario_id": "SCN-01",
                "station_id": "ST-001",
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "interval_minutes": 60,
                "predicted_arrivals": 10.0,
                "predicted_energy_kwh": 200.0,
                "model_version": "v1.0",
                "generated_at": base_start.isoformat(),
            })
        resp_payload = {
            "forecast_id": "FC-COMPL-01",
            "scenario_id": "SCN-01",
            "model_version": "v1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "intervals": intervals,
            "interval_count": 6,
            "station_ids": ["ST-001"],
        }
        return httpx.Response(200, json=resp_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    monkeypatch.setattr(httpx.Client, "get", mock_get)

    from app.schemas.forecast import ForecastCreateRequest

    provider = LiveForecastProvider(base_url="http://127.0.0.1:8001")
    req = ForecastCreateRequest(
        scenario_id="SCN-01",
        station_ids=["STN-01"],
        forecast_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_minutes=60,
        horizon_intervals=6,
    )
    ack = provider.create_forecast(req)
    assert ack.status == "completed"


def test_live_provider_create_forecast_unsupported_station_rejected():
    from app.schemas.forecast import ForecastCreateRequest
    from app.core.exceptions import StationMappingError

    provider = LiveForecastProvider(base_url="http://127.0.0.1:8001")
    # STN-04 is unsupported by the 3-station predictor model
    req = ForecastCreateRequest(
        scenario_id="SCN-01",
        station_ids=["STN-01", "STN-04"],
        forecast_start=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc),
        interval_minutes=60,
        horizon_intervals=6,
    )
    with pytest.raises(StationMappingError) as exc_info:
        provider.create_forecast(req)
    assert "not supported by the EVCharge-Predict model" in exc_info.value.message
