from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ScenarioBase(BaseModel):
    scenario_id: str = Field(..., min_length=1, max_length=64, description="Unique scenario ID")
    name: str = Field(..., min_length=1, max_length=128, description="Scenario title")
    description: Optional[str] = Field(None, description="Scenario description")
    selected_forecast_id: str = Field(..., min_length=1, max_length=64, description="Selected forecast identifier")
    planning_horizon_intervals: int = Field(default=6, ge=1, le=24, description="Number of planning intervals")
    provider_mode: str = Field(default="mock", description="Forecast provider mode ('mock' or 'live')")


class ScenarioCreate(ScenarioBase):
    pass


class ScenarioResponse(ScenarioBase):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
    allocation_count: Optional[int] = 0
