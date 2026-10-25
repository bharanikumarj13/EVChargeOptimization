from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class ForecastIntervalItem(BaseModel):
    model_config = {"protected_namespaces": ()}

    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: Optional[str] = Field(None, max_length=64)
    station_id: str = Field(..., min_length=1, max_length=64)
    interval_start: datetime
    interval_end: datetime
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    predicted_arrivals: float = Field(..., ge=0.0, description="Predicted arrival vehicles (>= 0)")
    predicted_energy_kwh: float = Field(..., ge=0.0, description="Predicted charging energy requirement in kWh (>= 0)")
    model_version: str = Field(default="v1.0", max_length=64)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_interval_timestamps(self):
        if self.interval_start >= self.interval_end:
            raise ValueError(
                f"interval_start ({self.interval_start}) must be before interval_end ({self.interval_end})"
            )
        duration_minutes = (self.interval_end - self.interval_start).total_seconds() / 60.0
        if abs(duration_minutes - self.interval_minutes) > 0.01:
            raise ValueError(
                f"Calculated duration {duration_minutes}m does not match interval_minutes ({self.interval_minutes}m)"
            )
        return self


class ForecastResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    forecast_id: str
    scenario_id: Optional[str] = None
    model_version: str
    generated_at: datetime
    intervals: List[ForecastIntervalItem]
    interval_count: int
    station_ids: List[str]
