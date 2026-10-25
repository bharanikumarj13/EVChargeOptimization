from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class StationFeedbackOutcome(BaseModel):
    station_id: str
    predicted_arrivals: float
    estimated_served: float
    estimated_unserved: float
    allocated_power_kw: float
    estimated_wait_minutes: Optional[float] = None
    charger_utilization_pct: float
    deferred_vehicles: float
    deferred_energy_kwh: float


class FeedbackCreateRequest(BaseModel):
    deferred_fraction: Optional[float] = Field(default=0.70, ge=0.0, le=1.0)
    idempotency_key: Optional[str] = Field(None, max_length=128)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_id: str
    scenario_id: str
    forecast_id: str
    allocation_id: str
    outcome_kind: str
    interval_start: datetime
    interval_end: datetime
    station_outcomes: List[StationFeedbackOutcome]
    deferred_fraction: float
    submission_status: str
    idempotency_key: str
    retry_count: int
    error_details: Optional[str] = None
    operational_adjustment_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
