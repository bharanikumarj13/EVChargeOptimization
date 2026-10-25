from app.core.config import settings
from app.integrations.base import ForecastProviderAdapter
from app.integrations.mock_provider import MockForecastProvider
from app.integrations.live_provider import LiveForecastProvider


_mock_instance = MockForecastProvider()


def get_forecast_provider() -> ForecastProviderAdapter:
    """Returns the configured forecast provider adapter (mock or live)."""
    if settings.is_mock_provider:
        return _mock_instance
    return LiveForecastProvider()


__all__ = [
    "ForecastProviderAdapter",
    "MockForecastProvider",
    "LiveForecastProvider",
    "get_forecast_provider",
]
