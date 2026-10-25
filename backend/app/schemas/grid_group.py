from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class GridGroupBase(BaseModel):
    grid_group_id: str = Field(..., min_length=1, max_length=64, description="Unique grid group ID")
    grid_group_name: str = Field(..., min_length=1, max_length=128, description="Human readable name")
    grid_limit_kw: float = Field(..., gt=0.0, description="Total grid capacity limit in kW")
    other_load_kw: float = Field(default=0.0, ge=0.0, description="Non-EV baseline or other load in kW")


class GridGroupCreate(GridGroupBase):
    pass


class GridGroupUpdate(BaseModel):
    grid_group_name: Optional[str] = Field(None, min_length=1, max_length=128)
    grid_limit_kw: Optional[float] = Field(None, gt=0.0)
    other_load_kw: Optional[float] = Field(None, ge=0.0)


class GridGroupResponse(GridGroupBase):
    model_config = ConfigDict(from_attributes=True)

    residual_capacity_kw: float
    created_at: datetime
    updated_at: datetime
