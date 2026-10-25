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
