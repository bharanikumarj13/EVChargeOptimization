import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.integrations.base import ForecastProviderAdapter
from app.schemas.forecast import ForecastResponse, ForecastIntervalItem
from app.core.config import settings
from app.core.exceptions import ProviderIntegrationError, EntityNotFoundError


class LiveForecastProvider(ForecastProviderAdapter):
    """
    HTTP client adapter communicating with the external EVCharge-Predict service over REST API.
    Enforces timeout, authentication, and safe error propagation.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_token: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.PREDICT_API_BASE_URL).rstrip("/")
        self.service_token = service_token or settings.PREDICT_SERVICE_TOKEN
        self.timeout = timeout or settings.PREDICT_TIMEOUT_SECONDS
        self._last_successful_request: Optional[str] = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "EVCharge-Opt/1.0",
        }
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"
        return headers

    def get_forecast(self, forecast_id: str, scenario_id: Optional[str] = None) -> ForecastResponse:
        url = f"{self.base_url}/api/v1/forecasts/{forecast_id}"
        params = {}
        if scenario_id:
            params["scenario_id"] = scenario_id

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers(), params=params)

                if response.status_code == 404:
                    raise EntityNotFoundError("Remote Forecast", forecast_id)

                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error: HTTP {response.status_code}",
                        is_retryable=True,
                    )
                if response.status_code != 200:
                    raise ProviderIntegrationError(
                        f"Failed to fetch forecast from predictor: HTTP {response.status_code}",
                        is_retryable=False,
                    )

                data = response.json()
                parsed = ForecastResponse.model_validate(data)
                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return parsed

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service connection failure: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/feedback"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=self._get_headers(), json=payload)
                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error during feedback submission: HTTP {response.status_code}",
                        is_retryable=True,
                    )
                if response.status_code not in (200, 201, 202):
                    raise ProviderIntegrationError(
                        f"Predictor rejected feedback submission: HTTP {response.status_code}",
                        is_retryable=False,
                    )

                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return response.json()

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service network error during feedback: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def get_next_operational_adjustment(
        self,
        feedback_id: str,
        target_interval_start: str,
        target_interval_end: str,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/operational-adjustments"
        params = {
            "source_feedback_id": feedback_id,
            "target_interval_start": target_interval_start,
            "target_interval_end": target_interval_end,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers(), params=params)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise ProviderIntegrationError(
                        f"Predictor error retrieving adjustment: HTTP {response.status_code}",
                        is_retryable=True,
                    )

                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return response.json()

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service network error retrieving adjustment: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def check_health(self) -> Dict[str, Any]:
        url = f"{self.base_url}/healthz"
        try:
            with httpx.Client(timeout=min(self.timeout, 5.0)) as client:
                response = client.get(url, headers=self._get_headers())
                is_healthy = response.status_code == 200
                if is_healthy:
                    self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return {
                    "status": "healthy" if is_healthy else "degraded",
                    "provider_mode": "live",
                    "is_mock": False,
                    "status_code": response.status_code,
                    "last_successful_request": self._last_successful_request,
                }
        except Exception as exc:
            return {
                "status": "unreachable",
                "provider_mode": "live",
                "is_mock": False,
                "error": exc.__class__.__name__,
                "last_successful_request": self._last_successful_request,
            }
