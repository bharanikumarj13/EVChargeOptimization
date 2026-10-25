from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class StationOperationalAdjustmentItem(BaseModel):
    station_id: str
    original_predicted_arrivals: float
    original_predicted_energy_kwh: float
    deferred_vehicles_added: float
    deferred_energy_kwh_added: float
    adjusted_predicted_arrivals: float
    adjusted_predicted_energy_kwh: float


class OperationalAdjustmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operational_adjustment_id: str
    source_feedback_id: str
    parent_forecast_id: str
    target_interval_start: datetime
    target_interval_end: datetime
    station_adjustments: List[StationOperationalAdjustmentItem]
    calculation_assumptions: Dict[str, Any]
    created_at: datetime
