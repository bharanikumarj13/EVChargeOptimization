from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.schemas.forecast import ForecastResponse, ForecastCreateRequest, ForecastAcknowledgement


class ForecastProviderAdapter(ABC):
    """Abstract interface defining operations with the EVCharge-Predict service."""

    @abstractmethod
    def create_forecast(self, req: ForecastCreateRequest) -> ForecastAcknowledgement:
        """Request generation of a new baseline forecast from the prediction service."""
        pass

    @abstractmethod
    def get_forecast(self, forecast_id: str, scenario_id: Optional[str] = None) -> ForecastResponse:
        """Fetch and validate a demand forecast by identifier."""
        pass

    @abstractmethod
    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit allocation outcome feedback to the prediction service."""
        pass

    @abstractmethod
    def get_next_operational_adjustment(
        self,
        feedback_id: str,
        target_interval_start: str,
        target_interval_end: str,
        forecast_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve operational demand adjustment for the subsequent interval."""
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Verify provider integration health without exposing credentials."""
        pass
