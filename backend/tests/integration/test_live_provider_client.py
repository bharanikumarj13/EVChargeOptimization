import pytest
from unittest.mock import patch
import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.integrations.live_provider import LiveForecastProvider
from app.core.exceptions import (
    ProviderIntegrationError,
    EntityNotFoundError,
    InvalidForecastError,
    IdempotencyConflictError,
)


@pytest.fixture(autouse=True)
def set_test_service_token(monkeypatch):
    monkeypatch.setattr(settings, "PREDICT_SERVICE_TOKEN", "mock-token-for-tests")


def test_live_provider_get_forecast_contract_success(monkeypatch):
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    intervals = []
    for i in range(6):
        s = base_start + timedelta(hours=i)
        e = s + timedelta(hours=1)
        intervals.append({
            "interval_start": s.isoformat(),
            "interval_end": e.isoformat(),
            "predicted_arrivals": 2 + i,  # Contract integer
            "predicted_energy_kwh": 34.5 + i * 5.0,  # Contract float
        })

    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "FC-LIVE-01",
        "scenario_id": "SCN-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [
            {
                "station_id": "ST-001",
                "intervals": intervals,
            }
        ],
        "model": {
            "model_version": "v2.0-neural",
            "training_data_type": "synthetic",
            "scikit_learn_version": "1.9.1",
            "training_data_fingerprint": "manifest_synthetic_fixtures_v1",
        },
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
    assert result.model_version == "v2.0-neural"
    assert result.station_ids == ["STN-01"]  # Mapped from canonical ST-001 to internal STN-01
    assert len(result.intervals) == 6
    assert result.intervals[0].station_id == "STN-01"
    assert result.intervals[0].predicted_arrivals == 2.0
    assert isinstance(result.intervals[0].predicted_arrivals, float)
    assert result.intervals[0].predicted_energy_kwh == 34.5
    assert result.intervals[0].interval_start.tzinfo == timezone.utc


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
        base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            intervals.append({
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "predicted_arrivals": 10 + i,
                "predicted_energy_kwh": 200.0 + i * 20.0,
            })
        resp_payload = {
            "contract_version": "1.0",
            "forecast_id": "FC-NEW-100",
            "scenario_id": "SCN-01",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "horizon": {
                "start": base_start.isoformat(),
                "end": (base_start + timedelta(hours=6)).isoformat(),
                "interval_minutes": 60,
                "interval_count": 6,
            },
            "demand_type": "baseline",
            "stations": [
                {
                    "station_id": "ST-001",
                    "intervals": intervals,
                }
            ],
            "model": {
                "model_version": "v1.0",
                "training_data_type": "synthetic",
                "scikit_learn_version": "1.9.1",
                "training_data_fingerprint": "manifest_synthetic_fixtures_v1",
            },
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


def _mock_originating_forecast_payload(base_start: datetime, forecast_id: str = "fcst_7a8b9c0d1e2f", station_id: str = "ST-001"):
    intervals = []
    for i in range(6):
        s = base_start + timedelta(hours=i)
        e = s + timedelta(hours=1)
        intervals.append({
            "interval_start": s.isoformat(),
            "interval_end": e.isoformat(),
            "predicted_arrivals": 2 + i,
            "predicted_energy_kwh": 30.0 + i * 5,
        })
    return {
        "contract_version": "1.0",
        "forecast_id": forecast_id,
        "scenario_id": "scenario_20261026_opt_run_01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [{"station_id": station_id, "intervals": intervals}],
        "model": {"model_version": "1.0", "training_data_type": "synthetic"},
    }


def test_live_provider_submit_feedback_http_201_success(monkeypatch):
    recorded_calls = []
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        recorded_calls.append(("POST", url, kwargs.get("json"), kwargs.get("headers")))
        resp_payload = {
            "contract_version": "1.0",
            "feedback_id": "fbk_1a2b3c4d5e6f",
            "allocation_run_id": "opt_run_20261026_001",
            "forecast_id": "fcst_7a8b9c0d1e2f",
            "scenario_id": "scenario_20261026_opt_run_01",
            "status": "accepted",
            "is_duplicate": False,
            "received_at": "2026-10-26T11:25:01Z",
            "feedback_url": "/api/v1/feedback/fbk_1a2b3c4d5e6f",
        }
        return httpx.Response(201, json=resp_payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(
        base_url="https://api.evcharge-predict.example.com",
        service_token="secret-token-123",
    )

    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "allocated_energy_kwh": 38.0 if i == 0 else None,
            "available_capacity_kw": 50.0 if i == 0 else None,
            "reported_unmet_demand_kwh": 0.0 if i == 0 else None,
        }
        for i in range(6)
    ]

    payload = {
        "allocation_run_id": "opt_run_20261026_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "submitted_at": "2026-10-26T11:25:00Z",
        "local_feedback_id": "FBD-LOCAL-01",
        "stations": [
            {
                "station_id": "STN-01",  # Internal station mapped to canonical ST-001
                "intervals": intervals,
            }
        ],
    }

    result = provider.submit_feedback(payload)

    assert result["status"] == "accepted"
    assert result["is_duplicate"] is False
    assert result["feedback_id"] == "fbk_1a2b3c4d5e6f"
    assert result["remote_feedback_id"] == "fbk_1a2b3c4d5e6f"
    assert result["local_feedback_id"] == "FBD-LOCAL-01"

    # Verify request payload
    assert len(recorded_calls) == 1
    post_url = recorded_calls[0][1]
    post_json = recorded_calls[0][2]
    headers = recorded_calls[0][3]

    assert post_url == "https://api.evcharge-predict.example.com/api/v1/feedback"
    assert headers["Authorization"] == "Bearer secret-token-123"
    assert post_json["allocation_run_id"] == "opt_run_20261026_001"
    assert post_json["stations"][0]["station_id"] == "ST-001"  # Mapped to canonical!
    assert len(post_json["stations"][0]["intervals"]) == 6


def test_live_provider_submit_feedback_http_200_identical_retry(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        resp_payload = {
            "contract_version": "1.0",
            "feedback_id": "fbk_1a2b3c4d5e6f",
            "allocation_run_id": "opt_run_20261026_001",
            "forecast_id": "fcst_7a8b9c0d1e2f",
            "scenario_id": "scenario_20261026_opt_run_01",
            "status": "accepted",
            "is_duplicate": True,  # Identical duplicate acknowledged with HTTP 200
            "received_at": "2026-10-26T11:25:01Z",
            "feedback_url": "/api/v1/feedback/fbk_1a2b3c4d5e6f",
        }
        return httpx.Response(200, json=resp_payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "allocated_energy_kwh": 38.0 if i == 0 else None,
            "available_capacity_kw": 50.0 if i == 0 else None,
            "reported_unmet_demand_kwh": 0.0 if i == 0 else None,
        }
        for i in range(6)
    ]

    payload = {
        "allocation_run_id": "opt_run_20261026_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "submitted_at": "2026-10-26T11:25:00Z",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
    }

    result = provider.submit_feedback(payload)
    assert result["is_duplicate"] is True
    assert result["feedback_id"] == "fbk_1a2b3c4d5e6f"


def test_live_provider_submit_feedback_http_409_conflict(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        error_detail = {
            "detail": "Allocation run 'opt_run_20261026_001' was already submitted with different content. Reusing the same run identifier with modified data is prohibited."
        }
        return httpx.Response(409, json=error_detail, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "allocated_energy_kwh": 99.0 if i == 0 else None,
        }
        for i in range(6)
    ]
    payload = {
        "allocation_run_id": "opt_run_20261026_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "submitted_at": "2026-10-26T11:25:00Z",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
    }

    with pytest.raises(IdempotencyConflictError) as exc_info:
        provider.submit_feedback(payload)

    assert "different content" in str(exc_info.value)
    assert exc_info.value.status_code == 409


def test_live_provider_submit_feedback_auth_error_non_retryable(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        return httpx.Response(403, text='{"detail": "Invalid or expired API authorization token."}', request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
        }
        for i in range(6)
    ]
    payload = {
        "allocation_run_id": "opt_run_20261026_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
    }

    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.submit_feedback(payload)

    assert exc_info.value.is_retryable is False
    assert "authentication failure" in exc_info.value.message.lower()


def test_live_provider_submit_feedback_partial_intervals_valid(monkeypatch):
    """
    Verifies that the predictor feedback API accepts partial interval sets (e.g. 1 or 2 intervals)
    without requiring all six intervals.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    recorded_posts = []

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        recorded_posts.append(kwargs.get("json"))
        resp_payload = {
            "contract_version": "1.0",
            "feedback_id": "fbk_partial_123",
            "allocation_run_id": "opt_run_partial_001",
            "forecast_id": "fcst_7a8b9c0d1e2f",
            "scenario_id": "scenario_20261026_opt_run_01",
            "status": "accepted",
            "is_duplicate": False,
            "received_at": "2026-10-26T12:00:00Z",
            "feedback_url": "/api/v1/feedback/fbk_partial_123",
        }
        return httpx.Response(201, json=resp_payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # Submit only 1 interval for ST-001 (partial set)
    single_interval = [
        {
            "interval_start": base_start.isoformat(),
            "interval_end": (base_start + timedelta(hours=1)).isoformat(),
            "allocated_energy_kwh": 42.5,
            "available_capacity_kw": 50.0,
            "reported_unmet_demand_kwh": 0.0,
        }
    ]
    payload = {
        "allocation_run_id": "opt_run_partial_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "stations": [{"station_id": "ST-001", "intervals": single_interval}],
    }

    result = provider.submit_feedback(payload)

    assert result["status"] == "accepted"
    assert result["is_duplicate"] is False
    assert result["feedback_id"] == "fbk_partial_123"

    assert len(recorded_posts) == 1
    post_data = recorded_posts[0]
    stn_intervals = post_data["stations"][0]["intervals"]
    # Exactly 1 interval sent, no 5 null intervals padded
    assert len(stn_intervals) == 1
    assert stn_intervals[0]["allocated_energy_kwh"] == 42.5


def test_live_provider_submit_feedback_interval_mismatch_rejected(monkeypatch):
    """
    Verifies that submitted intervals whose timestamps do not match the originating forecast boundaries
    are rejected with InvalidForecastError.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # Interval not aligned with the originating forecast (e.g. 12:30 to 13:30 instead of 12:00 to 13:00)
    misaligned_interval = [
        {
            "interval_start": (base_start + timedelta(minutes=30)).isoformat(),
            "interval_end": (base_start + timedelta(minutes=90)).isoformat(),
            "allocated_energy_kwh": 20.0,
        }
    ]
    payload = {
        "allocation_run_id": "opt_run_err_001",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "stations": [{"station_id": "ST-001", "intervals": misaligned_interval}],
    }

    with pytest.raises(InvalidForecastError) as exc_info:
        provider.submit_feedback(payload)

    assert "does not match any interval in originating forecast" in exc_info.value.message


def test_live_provider_submit_feedback_station_mismatch_rejected(monkeypatch):
    """
    Verifies that submitting feedback for a station not part of the originating forecast
    is rejected with InvalidForecastError.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Originating forecast only contains ST-001
    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start, station_id="ST-001"), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    payload = {
        "allocation_run_id": "opt_run_err_002",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        # Station ST-002 is not in the originating forecast
        "stations": [
            {
                "station_id": "ST-002",
                "intervals": [
                    {
                        "interval_start": base_start.isoformat(),
                        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
                    }
                ],
            }
        ],
    }

    with pytest.raises(InvalidForecastError) as exc_info:
        provider.submit_feedback(payload)

    assert "is not part of originating forecast" in exc_info.value.message


def test_live_provider_submit_feedback_empty_intervals_rejected(monkeypatch):
    """
    Verifies that submitting an empty interval list for a station is rejected.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    payload = {
        "allocation_run_id": "opt_run_err_003",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "stations": [{"station_id": "ST-001", "intervals": []}],
    }

    with pytest.raises((InvalidForecastError, Exception)) as exc_info:
        provider.submit_feedback(payload)

    assert "must contain at least one feedback interval" in str(exc_info.value)


def test_live_provider_submit_feedback_with_station_outcomes_fetches_forecast(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Mock GET forecast call to supply the 6 baseline intervals
    def mock_get(self, url, **kwargs):
        forecast_intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            forecast_intervals.append({
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "predicted_arrivals": 2 + i,
                "predicted_energy_kwh": 30.0 + i * 5,
            })
        resp_payload = {
            "contract_version": "1.0",
            "forecast_id": "fcst_7a8b9c0d1e2f",
            "scenario_id": "scenario_01",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "horizon": {
                "start": base_start.isoformat(),
                "end": (base_start + timedelta(hours=6)).isoformat(),
                "interval_minutes": 60,
                "interval_count": 6,
            },
            "demand_type": "baseline",
            "stations": [{"station_id": "ST-001", "intervals": forecast_intervals}],
            "model": {"model_version": "1.0", "training_data_type": "synthetic"},
        }
        return httpx.Response(200, json=resp_payload, request=httpx.Request("GET", url))

    recorded_posts = []

    def mock_post(self, url, **kwargs):
        recorded_posts.append(kwargs.get("json"))
        return httpx.Response(
            201,
            json={
                "contract_version": "1.0",
                "feedback_id": "fbk_created_999",
                "allocation_run_id": "ALC-100",
                "forecast_id": "fcst_7a8b9c0d1e2f",
                "scenario_id": "scenario_01",
                "status": "accepted",
                "is_duplicate": False,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "feedback_url": "/api/v1/feedback/fbk_created_999",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    payload = {
        "allocation_id": "ALC-100",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "interval_start": base_start.isoformat(),
        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
        "station_outcomes": [
            {
                "station_id": "STN-01",
                "estimated_served_energy_kwh": 38.0,
                "allocated_power_kw": 50.0,
                "estimated_unserved_energy_kwh": 2.5,
                "predicted_arrivals": 2.0,  # vehicle count, must NOT be confused with energy
                "estimated_unserved": 1.0,  # vehicle count, must NOT be confused with energy
            }
        ],
    }

    res = provider.submit_feedback(payload)
    assert res["feedback_id"] == "fbk_created_999"
    assert len(recorded_posts) == 1
    post_json = recorded_posts[0]
    stn_invs = post_json["stations"][0]["intervals"]
    # Partial feedback: exactly 1 evaluated interval without null padding!
    assert len(stn_invs) == 1

    # First interval has the active allocation metrics
    assert stn_invs[0]["allocated_energy_kwh"] == 38.0
    assert stn_invs[0]["available_capacity_kw"] == 50.0
    assert stn_invs[0]["reported_unmet_demand_kwh"] == 2.5


def test_live_provider_get_next_operational_adjustment_contract_success(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "baseline_arrivals": 2 + i,
            "baseline_energy_kwh": 34.5 + i * 5.0,
            "allocated_energy_kwh": 40.0 if i == 0 else 15.0,
            "available_capacity_kw": 50.0,
            "reported_unmet_demand_kwh": 0.0,
            "adjusted_operational_demand_kwh": 40.0 if i == 0 else (34.5 + i * 5.0),
            "adjustment_status": "adjusted" if i == 0 else "unchanged",
        }
        for i in range(6)
    ]

    mock_resp = {
        "contract_version": "1.0",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "feedback_id": "fbk_1a2b3c4d5e6f",
        "allocation_run_id": "opt_run_01",
        "demand_type": "feedback-adjusted-operational",
        "adjustment_policy_version": "v1-heuristic-operational-envelope",
        "policy_description": "Operational demand envelope taking max(baseline, allocated).",
        "policy_limitations": "Does not reflect verified ground-truth demand.",
        "computed_at": "2026-10-26T11:25:01Z",
        "stations": [
            {
                "station_id": "ST-001",
                "intervals": intervals,
            }
        ],
    }

    recorded_calls = []

    def mock_get(self, url, **kwargs):
        recorded_calls.append((url, kwargs.get("params")))
        return httpx.Response(200, json=mock_resp, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    # Pre-map local feedback ID to remote feedback ID
    provider._local_to_remote_feedback_ids["FBD-LOCAL-123"] = "fbk_1a2b3c4d5e6f"

    res = provider.get_next_operational_adjustment(
        feedback_id="FBD-LOCAL-123",  # Local ID resolved to remote!
        target_interval_start=(base_start + timedelta(hours=1)).isoformat(),
        target_interval_end=(base_start + timedelta(hours=2)).isoformat(),
        forecast_id="fcst_7a8b9c0d1e2f",
    )

    assert res is not None
    assert len(recorded_calls) == 1
    call_url, call_params = recorded_calls[0]
    assert call_url == "https://api.evcharge-predict.example.com/api/v1/forecasts/fcst_7a8b9c0d1e2f/adjusted-demand"
    assert call_params == {"feedback_id": "fbk_1a2b3c4d5e6f"}  # Preserved remote predictor ID!

    # Check station adjustments
    adj_items = res["station_adjustments"]
    assert len(adj_items) == 1
    item = adj_items[0]
    assert item["station_id"] == "STN-01"  # Mapped to internal STN-01!
    # For interval index 1: baseline_arrivals = 3, baseline_energy_kwh = 39.5
    assert item["original_predicted_arrivals"] == 3.0
    assert item["original_predicted_energy_kwh"] == 39.5
    assert item["adjusted_predicted_arrivals"] == 3.0  # Arrivals strictly preserved from baseline
    assert item["adjusted_predicted_energy_kwh"] == 39.5


def test_live_provider_get_next_operational_adjustment_target_interval_not_found(monkeypatch):
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    mock_resp = {
        "contract_version": "1.0",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "feedback_id": "fbk_1a2b3c4d5e6f",
        "allocation_run_id": "opt_run_01",
        "demand_type": "feedback-adjusted-operational",
        "adjustment_policy_version": "v1-heuristic-operational-envelope",
        "policy_description": "Envelope",
        "policy_limitations": "Limitations",
        "computed_at": "2026-10-26T11:25:01Z",
        "stations": [
            {
                "station_id": "ST-001",
                "intervals": [
                    {
                        "interval_start": (base_start + timedelta(hours=i)).isoformat(),
                        "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
                        "baseline_arrivals": 2,
                        "baseline_energy_kwh": 30.0,
                        "adjusted_operational_demand_kwh": 30.0,
                        "adjustment_status": "unchanged",
                    }
                    for i in range(6)
                ],
            }
        ],
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_resp, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_1a2b3c4d5e6f",
            target_interval_start="2026-10-26T22:00:00Z",  # Outside horizon
            target_interval_end="2026-10-26T23:00:00Z",
            forecast_id="fcst_7a8b9c0d1e2f",
        )
    assert "was not found in predictor adjusted demand intervals" in exc_info.value.message


def test_live_provider_get_next_operational_adjustment_404_returns_none(monkeypatch):
    def mock_get(self, url, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    res = provider.get_next_operational_adjustment(
        feedback_id="fbk_not_found",
        target_interval_start="2026-10-26T12:00:00Z",
        target_interval_end="2026-10-26T13:00:00Z",
        forecast_id="fcst_unknown",
    )
    assert res is None


def test_live_provider_get_next_operational_adjustment_auth_failure(monkeypatch):
    def mock_get(self, url, **kwargs):
        return httpx.Response(401, text="Unauthorized", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(ProviderIntegrationError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_auth_fail",
            target_interval_start="2026-10-26T12:00:00Z",
            target_interval_end="2026-10-26T13:00:00Z",
            forecast_id="fcst_test",
        )
    assert exc_info.value.is_retryable is False
    assert "authentication failure" in exc_info.value.message.lower()


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
        base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        intervals = []
        for i in range(6):
            s = base_start + timedelta(hours=i)
            e = s + timedelta(hours=1)
            intervals.append({
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "predicted_arrivals": 10,
                "predicted_energy_kwh": 200.0,
            })
        resp_payload = {
            "contract_version": "1.0",
            "forecast_id": "FC-COMPL-01",
            "scenario_id": "SCN-01",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "horizon": {
                "start": base_start.isoformat(),
                "end": (base_start + timedelta(hours=6)).isoformat(),
                "interval_minutes": 60,
                "interval_count": 6,
            },
            "demand_type": "baseline",
            "stations": [
                {
                    "station_id": "ST-001",
                    "intervals": intervals,
                }
            ],
            "model": {
                "model_version": "v1.0",
                "training_data_type": "synthetic",
            },
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


def test_live_provider_three_station_contract_parsing(monkeypatch):
    """
    Verifies full 3-station contract response parsing with nested intervals,
    mapping from canonical ST-001, ST-002, ST-003 to internal STN-01, STN-02, STN-03.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    stations_data = []
    canonical_stations = ["ST-001", "ST-002", "ST-003"]

    for idx, stn_id in enumerate(canonical_stations):
        intervals = []
        for h in range(6):
            s = base_start + timedelta(hours=h)
            e = s + timedelta(hours=1)
            intervals.append({
                "interval_start": s.isoformat(),
                "interval_end": e.isoformat(),
                "predicted_arrivals": (idx + 1) * 2 + h,
                "predicted_energy_kwh": 30.0 + (idx * 15.0) + (h * 4.5),
            })
        stations_data.append({
            "station_id": stn_id,
            "intervals": intervals,
        })

    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "fcst_three_stn_777",
        "scenario_id": "scenario_three_stn_demo",
        "generated_at": "2026-10-26T11:20:00Z",
        "horizon": {
            "start": "2026-10-26T12:00:00Z",
            "end": "2026-10-26T18:00:00Z",
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": stations_data,
        "model": {
            "model_version": "1.0",
            "training_data_type": "synthetic",
            "scikit_learn_version": "1.9.1",
            "training_data_fingerprint": "manifest_synthetic_fixtures_v1",
        },
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    result = provider.get_forecast("fcst_three_stn_777")

    assert result.forecast_id == "fcst_three_stn_777"
    assert result.scenario_id == "scenario_three_stn_demo"
    assert result.model_version == "1.0"
    assert result.station_ids == ["STN-01", "STN-02", "STN-03"]
    assert len(result.intervals) == 18
    assert result.interval_count == 18

    # Verify each station has exactly 6 consecutive intervals
    for internal_stn in ["STN-01", "STN-02", "STN-03"]:
        stn_items = [it for it in result.intervals if it.station_id == internal_stn]
        assert len(stn_items) == 6
        for idx, item in enumerate(stn_items):
            assert isinstance(item.predicted_arrivals, float)
            assert item.predicted_arrivals >= 0.0
            assert isinstance(item.predicted_energy_kwh, float)
            assert item.predicted_energy_kwh >= 0.0
            assert item.interval_start.tzinfo == timezone.utc
            assert item.interval_end.tzinfo == timezone.utc
            if idx > 0:
                assert item.interval_start == stn_items[idx - 1].interval_end


def test_live_provider_rejects_fewer_than_six_intervals(monkeypatch):
    """Verifies that an error is raised when a station returns fewer than 6 intervals."""
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    # Only 5 intervals for ST-001
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "predicted_arrivals": 2,
            "predicted_energy_kwh": 30.0,
        }
        for i in range(5)
    ]
    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "FC-FAIL-COUNT",
        "scenario_id": "SCN-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
        "model": {"model_version": "1.0", "training_data_type": "synthetic"},
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_forecast("FC-FAIL-COUNT")
    assert "returned 5 intervals, expected exactly 6" in exc_info.value.message


def test_live_provider_rejects_non_consecutive_intervals(monkeypatch):
    """Verifies that non-consecutive intervals (with a 1-hour gap) are rejected."""
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    intervals = []
    for i in range(6):
        # Introduce a gap at interval index 2 (skips 10:00 to 11:00)
        offset = i if i < 2 else i + 1
        s = base_start + timedelta(hours=offset)
        e = s + timedelta(hours=1)
        intervals.append({
            "interval_start": s.isoformat(),
            "interval_end": e.isoformat(),
            "predicted_arrivals": 2,
            "predicted_energy_kwh": 30.0,
        })

    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "FC-FAIL-GAP",
        "scenario_id": "SCN-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=7)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
        "model": {"model_version": "1.0", "training_data_type": "synthetic"},
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_forecast("FC-FAIL-GAP")
    assert "Non-consecutive or overlapping intervals" in exc_info.value.message


def test_live_provider_rejects_negative_predictions(monkeypatch):
    """Verifies that negative arrival counts or energy values are rejected."""
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "predicted_arrivals": -3 if i == 0 else 2,  # Negative arrivals
            "predicted_energy_kwh": 30.0,
        }
        for i in range(6)
    ]
    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "FC-FAIL-NEG",
        "scenario_id": "SCN-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [{"station_id": "ST-001", "intervals": intervals}],
        "model": {"model_version": "1.0", "training_data_type": "synthetic"},
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(InvalidForecastError):
        provider.get_forecast("FC-FAIL-NEG")


def test_live_provider_rejects_unmapped_external_station(monkeypatch):
    """Verifies that external station IDs with no mapping to internal stations are rejected."""
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    intervals = [
        {
            "interval_start": (base_start + timedelta(hours=i)).isoformat(),
            "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
            "predicted_arrivals": 2,
            "predicted_energy_kwh": 30.0,
        }
        for i in range(6)
    ]
    mock_payload = {
        "contract_version": "1.0",
        "forecast_id": "FC-FAIL-UNKNOWN-STN",
        "scenario_id": "SCN-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon": {
            "start": base_start.isoformat(),
            "end": (base_start + timedelta(hours=6)).isoformat(),
            "interval_minutes": 60,
            "interval_count": 6,
        },
        "demand_type": "baseline",
        "stations": [{"station_id": "ST-UNKNOWN-999", "intervals": intervals}],
        "model": {"model_version": "1.0", "training_data_type": "synthetic"},
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_forecast("FC-FAIL-UNKNOWN-STN")
    assert "cannot be mapped to any internal station" in exc_info.value.message


def test_live_provider_backward_compatibility_flat_payload(monkeypatch):
    """Verifies backward compatibility with flat intervals payload."""
    base_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    mock_payload = {
        "forecast_id": "FC-LEGACY-01",
        "scenario_id": "SCN-01",
        "model_version": "legacy-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intervals": [
            {
                "forecast_id": "FC-LEGACY-01",
                "scenario_id": "SCN-01",
                "station_id": "ST-001",  # External ID
                "interval_start": base_start.isoformat(),
                "interval_end": (base_start + timedelta(hours=1)).isoformat(),
                "interval_minutes": 60,
                "predicted_arrivals": 5.0,
                "predicted_energy_kwh": 100.0,
                "model_version": "legacy-v1",
                "generated_at": (base_start - timedelta(hours=1)).isoformat(),
            }
        ],
        "interval_count": 1,
        "station_ids": ["ST-001"],
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    result = provider.get_forecast("FC-LEGACY-01")
    assert result.forecast_id == "FC-LEGACY-01"
    assert result.station_ids == ["STN-01"]  # Mapped from ST-001 to STN-01
    assert result.intervals[0].station_id == "STN-01"
    assert result.intervals[0].predicted_arrivals == 5.0


def test_live_provider_submit_feedback_preserves_zero_numeric_fallbacks(monkeypatch):
    """
    Requirement 1 regression test: Valid zero values for allocated_energy_kwh,
    available_capacity_kw, and reported_unmet_demand_kwh must be preserved and not
    fall back to alternative keys via truthiness or-chains.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    recorded_posts = []

    def mock_post(self, url, **kwargs):
        recorded_posts.append(kwargs.get("json"))
        return httpx.Response(
            201,
            json={
                "contract_version": "1.0",
                "feedback_id": "fbk_zero_001",
                "allocation_run_id": "ALC-ZERO",
                "forecast_id": "fcst_7a8b9c0d1e2f",
                "scenario_id": "scenario_01",
                "status": "accepted",
                "is_duplicate": False,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "feedback_url": "/api/v1/feedback/fbk_zero_001",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # Case A: Explicit 0.0 values with non-zero fallback alternatives present
    payload_zeros = {
        "allocation_id": "ALC-ZERO",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "interval_start": base_start.isoformat(),
        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
        "station_outcomes": [
            {
                "station_id": "STN-01",
                "allocated_energy_kwh": 0.0,
                "estimated_served_energy_kwh": 45.0,  # Must NOT overwrite 0.0
                "available_capacity_kw": 0.0,
                "allocated_power_kw": 50.0,  # Must NOT overwrite 0.0
                "reported_unmet_demand_kwh": 0.0,
                "estimated_unserved_energy_kwh": 12.0,  # Must NOT overwrite 0.0
                "deferred_energy_kwh": 6.0,  # Must NOT overwrite 0.0
            }
        ],
    }

    res = provider.submit_feedback(payload_zeros)
    assert res["feedback_id"] == "fbk_zero_001"
    assert len(recorded_posts) == 1
    post_json = recorded_posts[0]
    inv = post_json["stations"][0]["intervals"][0]

    # Explicit 0.0 values must be preserved!
    assert inv["allocated_energy_kwh"] == 0.0
    assert inv["available_capacity_kw"] == 0.0
    assert inv["reported_unmet_demand_kwh"] == 0.0

    # Case B: When primary key is None, safe fallback to secondary keys works
    payload_fallback = {
        "allocation_id": "ALC-FALLBACK",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "interval_start": base_start.isoformat(),
        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
        "station_outcomes": [
            {
                "station_id": "STN-01",
                "allocated_energy_kwh": None,
                "estimated_served_energy_kwh": 45.0,  # Should be used
                "available_capacity_kw": None,
                "allocated_power_kw": 50.0,  # Should be used
                "reported_unmet_demand_kwh": None,
                "estimated_unserved_energy_kwh": 12.0,  # Should be used
            }
        ],
    }
    provider.submit_feedback(payload_fallback)
    assert len(recorded_posts) == 2
    inv2 = recorded_posts[1]["stations"][0]["intervals"][0]
    assert inv2["allocated_energy_kwh"] == 45.0
    assert inv2["available_capacity_kw"] == 50.0
    assert inv2["reported_unmet_demand_kwh"] == 12.0


def test_live_provider_submit_feedback_rejects_slight_boundary_deviation(monkeypatch):
    """
    Requirement 2 regression test: Boundary matching must not silently accept deviations
    under a 60-second tolerance. Even slight deviations (e.g. 15 seconds) must be rejected.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # 15 seconds offset from exact 12:00:00 to 13:00:00 boundary in stations format
    deviated_interval = [
        {
            "interval_start": (base_start + timedelta(seconds=15)).isoformat(),
            "interval_end": (base_start + timedelta(hours=1, seconds=15)).isoformat(),
            "allocated_energy_kwh": 30.0,
        }
    ]
    payload = {
        "allocation_run_id": "opt_run_slight_err",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_20261026_opt_run_01",
        "stations": [{"station_id": "ST-001", "intervals": deviated_interval}],
    }

    with pytest.raises(InvalidForecastError) as exc_info:
        provider.submit_feedback(payload)

    assert "does not match any interval in originating forecast" in exc_info.value.message

    # Also test station_outcomes format with 10-second deviation
    payload_outcomes_dev = {
        "allocation_id": "ALC-SLIGHT",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "interval_start": (base_start + timedelta(seconds=10)).isoformat(),
        "interval_end": (base_start + timedelta(hours=1, seconds=10)).isoformat(),
        "station_outcomes": [{"station_id": "STN-01", "allocated_energy_kwh": 20.0}],
    }
    with pytest.raises(InvalidForecastError) as exc_info2:
        provider.submit_feedback(payload_outcomes_dev)
    assert "does not match any interval in originating forecast" in exc_info2.value.message


def test_live_provider_submit_feedback_accepts_timezone_equivalent_timestamps(monkeypatch):
    """
    Requirement 2 regression test: Intervals submitted in non-UTC timezone offsets that
    represent the exact same UTC instants must match and be normalized to canonical UTC.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    recorded_posts = []

    def mock_post(self, url, **kwargs):
        recorded_posts.append(kwargs.get("json"))
        return httpx.Response(
            201,
            json={
                "contract_version": "1.0",
                "feedback_id": "fbk_tz_001",
                "allocation_run_id": "ALC-TZ",
                "forecast_id": "fcst_7a8b9c0d1e2f",
                "scenario_id": "scenario_01",
                "status": "accepted",
                "is_duplicate": False,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "feedback_url": "/api/v1/feedback/fbk_tz_001",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # 17:30:00+05:30 is exactly 12:00:00 UTC; 18:30:00+05:30 is exactly 13:00:00 UTC
    tz_interval = [
        {
            "interval_start": "2026-10-26T17:30:00+05:30",
            "interval_end": "2026-10-26T18:30:00+05:30",
            "allocated_energy_kwh": 35.0,
            "available_capacity_kw": 50.0,
            "reported_unmet_demand_kwh": 0.0,
        }
    ]
    payload = {
        "allocation_run_id": "ALC-TZ",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "stations": [{"station_id": "ST-001", "intervals": tz_interval}],
    }

    res = provider.submit_feedback(payload)
    assert res["status"] == "accepted"
    assert len(recorded_posts) == 1
    post_json = recorded_posts[0]
    posted_inv = post_json["stations"][0]["intervals"][0]
    # Boundaries matched and normalized to canonical UTC
    assert posted_inv["interval_start"] == "2026-10-26T12:00:00Z"
    assert posted_inv["interval_end"] == "2026-10-26T13:00:00Z"

    # Also test station_outcomes format with -04:00 offset (EDT)
    # 08:00:00-04:00 is exactly 12:00:00 UTC; 09:00:00-04:00 is exactly 13:00:00 UTC
    payload_edt = {
        "allocation_id": "ALC-EDT",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "interval_start": "2026-10-26T08:00:00-04:00",
        "interval_end": "2026-10-26T09:00:00-04:00",
        "station_outcomes": [{"station_id": "STN-01", "allocated_energy_kwh": 28.0}],
    }
    res_edt = provider.submit_feedback(payload_edt)
    assert res_edt["status"] == "accepted"
    assert len(recorded_posts) == 2
    posted_inv_edt = recorded_posts[1]["stations"][0]["intervals"][0]
    assert posted_inv_edt["interval_start"] == "2026-10-26T12:00:00Z"
    assert posted_inv_edt["interval_end"] == "2026-10-26T13:00:00Z"


def test_live_provider_get_next_operational_adjustment_enforces_both_boundaries(monkeypatch):
    """
    Requirement 3 regression test: Both target_interval_start and target_interval_end
    must match the same forecast interval exactly in adjusted demand retrieval.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
    mock_resp = {
        "contract_version": "1.0",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "feedback_id": "fbk_adj_test",
        "allocation_run_id": "opt_run_01",
        "demand_type": "feedback-adjusted-operational",
        "adjustment_policy_version": "v1-heuristic-operational-envelope",
        "policy_description": "Envelope",
        "policy_limitations": "Limitations",
        "computed_at": "2026-10-26T11:25:01Z",
        "stations": [
            {
                "station_id": "ST-001",
                "intervals": [
                    {
                        "interval_start": (base_start + timedelta(hours=i)).isoformat(),
                        "interval_end": (base_start + timedelta(hours=i + 1)).isoformat(),
                        "baseline_arrivals": 2 + i,
                        "baseline_energy_kwh": 30.0 + i * 5.0,
                        "adjusted_operational_demand_kwh": 30.0 + i * 5.0,
                        "adjustment_status": "unchanged",
                    }
                    for i in range(6)
                ],
            }
        ],
    }

    def mock_get(self, url, **kwargs):
        return httpx.Response(200, json=mock_resp, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    provider = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # Case 1: Start matches (12:00:00Z), but end is mismatched (14:00:00Z instead of 13:00:00Z)
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_adj_test",
            target_interval_start="2026-10-26T12:00:00Z",
            target_interval_end="2026-10-26T14:00:00Z",  # 2 hours instead of 1 hour
            forecast_id="fcst_7a8b9c0d1e2f",
        )
    assert "was not found in predictor adjusted demand intervals" in exc_info.value.message

    # Case 2: End matches (13:00:00Z), but start is mismatched (11:00:00Z)
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_adj_test",
            target_interval_start="2026-10-26T11:00:00Z",
            target_interval_end="2026-10-26T13:00:00Z",
            forecast_id="fcst_7a8b9c0d1e2f",
        )
    assert "was not found in predictor adjusted demand intervals" in exc_info.value.message

    # Case 3: Inverted timestamps (start >= end)
    with pytest.raises(InvalidForecastError) as exc_info:
        provider.get_next_operational_adjustment(
            feedback_id="fbk_adj_test",
            target_interval_start="2026-10-26T13:00:00Z",
            target_interval_end="2026-10-26T12:00:00Z",
            forecast_id="fcst_7a8b9c0d1e2f",
        )
    assert "must be before target_interval_end" in exc_info.value.message

    # Case 4: Timezone-equivalent start and end (17:30:00+05:30 to 18:30:00+05:30 matches 12:00:00Z to 13:00:00Z)
    res = provider.get_next_operational_adjustment(
        feedback_id="fbk_adj_test",
        target_interval_start="2026-10-26T17:30:00+05:30",
        target_interval_end="2026-10-26T18:30:00+05:30",
        forecast_id="fcst_7a8b9c0d1e2f",
    )
    assert res is not None
    assert len(res["station_adjustments"]) == 1
    assert res["station_adjustments"][0]["original_predicted_arrivals"] == 2.0


def test_live_provider_feedback_id_mapping_shared_across_instances(monkeypatch):
    """
    Requirement 4 regression test: Verifies that in-memory feedback ID mapping
    is shared across LiveForecastProvider instances in the runtime environment.
    """
    base_start = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    def mock_get(self, url, **kwargs):
        if "adjusted-demand" in url:
            return httpx.Response(
                200,
                json={
                    "contract_version": "1.0",
                    "forecast_id": "fcst_7a8b9c0d1e2f",
                    "scenario_id": "scenario_01",
                    "feedback_id": "fbk_remote_shared_777",
                    "allocation_run_id": "ALC-SHARED",
                    "demand_type": "feedback-adjusted-operational",
                    "adjustment_policy_version": "v1",
                    "policy_description": "desc",
                    "policy_limitations": "lim",
                    "computed_at": "2026-10-26T11:25:01Z",
                    "stations": [
                        {
                            "station_id": "ST-001",
                            "intervals": [
                                {
                                    "interval_start": base_start.isoformat(),
                                    "interval_end": (base_start + timedelta(hours=1)).isoformat(),
                                    "baseline_arrivals": 5,
                                    "baseline_energy_kwh": 50.0,
                                    "adjusted_operational_demand_kwh": 50.0,
                                    "adjustment_status": "unchanged",
                                }
                            ],
                        }
                    ],
                },
                request=httpx.Request("GET", url),
            )
        return httpx.Response(200, json=_mock_originating_forecast_payload(base_start), request=httpx.Request("GET", url))

    def mock_post(self, url, **kwargs):
        return httpx.Response(
            201,
            json={
                "contract_version": "1.0",
                "feedback_id": "fbk_remote_shared_777",
                "allocation_run_id": "ALC-SHARED",
                "forecast_id": "fcst_7a8b9c0d1e2f",
                "scenario_id": "scenario_01",
                "status": "accepted",
                "is_duplicate": False,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "feedback_url": "/api/v1/feedback/fbk_remote_shared_777",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider1 = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")
    payload = {
        "allocation_id": "ALC-SHARED",
        "forecast_id": "fcst_7a8b9c0d1e2f",
        "scenario_id": "scenario_01",
        "local_feedback_id": "FBD-LOCAL-SHARED-123",
        "interval_start": base_start.isoformat(),
        "interval_end": (base_start + timedelta(hours=1)).isoformat(),
        "station_outcomes": [
            {
                "station_id": "STN-01",
                "allocated_energy_kwh": 40.0,
                "available_capacity_kw": 50.0,
                "reported_unmet_demand_kwh": 0.0,
            }
        ],
    }
    provider1.submit_feedback(payload)

    # Instantiate a completely separate provider instance
    provider2 = LiveForecastProvider(base_url="https://api.evcharge-predict.example.com")

    # Verify provider2 resolves the local ID mapped by provider1
    res = provider2.get_next_operational_adjustment(
        feedback_id="FBD-LOCAL-SHARED-123",  # Local ID resolved to remote!
        target_interval_start=base_start.isoformat(),
        target_interval_end=(base_start + timedelta(hours=1)).isoformat(),
        forecast_id="fcst_7a8b9c0d1e2f",
    )
    assert res is not None
    assert res["source_feedback_id"] == "FBD-LOCAL-SHARED-123"
