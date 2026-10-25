from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


class StationBase(BaseModel):
    station_id: str = Field(..., min_length=1, max_length=64, description="Unique station ID")
    station_name: str = Field(..., min_length=1, max_length=128, description="Station name")
    charger_count: int = Field(..., ge=1, description="Total installed chargers (>= 1)")
    available_chargers: int = Field(..., ge=0, description="Available operational chargers")
    charger_power_kw_per_charger: float = Field(..., gt=0.0, description="Rating per charger in kW")
    station_power_limit_kw: float = Field(..., gt=0.0, description="Station connection power limit in kW")
    avg_session_minutes: float = Field(default=45.0, gt=0.0, description="Average session duration in minutes")
    grid_group_id: str = Field(..., min_length=1, max_length=64, description="Associated grid group")
    is_active: bool = Field(default=True, description="Whether station is currently active")

    @model_validator(mode="after")
    def validate_chargers_and_power(self):
        if self.available_chargers > self.charger_count:
            raise ValueError(
                f"available_chargers ({self.available_chargers}) cannot exceed charger_count ({self.charger_count})"
            )
        return self


class StationCreate(StationBase):
    pass


class StationUpdate(BaseModel):
    station_name: Optional[str] = Field(None, min_length=1, max_length=128)
    charger_count: Optional[int] = Field(None, ge=1)
    available_chargers: Optional[int] = Field(None, ge=0)
    charger_power_kw_per_charger: Optional[float] = Field(None, gt=0.0)
    station_power_limit_kw: Optional[float] = Field(None, gt=0.0)
    avg_session_minutes: Optional[float] = Field(None, gt=0.0)
    grid_group_id: Optional[str] = Field(None, min_length=1, max_length=64)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_update(self):
        if self.available_chargers is not None and self.charger_count is not None:
            if self.available_chargers > self.charger_count:
                raise ValueError("available_chargers cannot exceed charger_count")
        return self


class StationResponse(StationBase):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
