from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AllocationRunRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1, max_length=64)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    interval_start: datetime
    interval_end: datetime
    operational_adjustment_id: Optional[str] = Field(None, max_length=64)


class StationAllocationResultSchema(BaseModel):
    station_id: str
    station_name: Optional[str] = None
    predicted_arrivals: float
    predicted_energy_kwh: float
    estimated_served: float
    estimated_unserved: float
    allocated_power_kw: float
    estimated_served_energy_kwh: float
    estimated_unserved_energy_kwh: float
    estimated_wait_minutes: Optional[float] = None
    charger_utilization_pct: float
    warnings: List[str] = []


class AllocationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allocation_id: str
    scenario_id: str
    forecast_id: str
    operational_adjustment_id: Optional[str] = None
    interval_start: datetime
    interval_end: datetime
    status: str
    outcome_kind: str
    algorithm_version: str
    objective_description: str
    constraint_validation_passed: bool
    warnings: List[str] = []
    results: List[StationAllocationResultSchema]
    created_at: datetime


class AllocationRunSummary(BaseModel):
    allocation_id: str
    scenario_id: str
    forecast_id: str
    operational_adjustment_id: Optional[str] = None
    interval_start: datetime
    interval_end: datetime
    status: str
    outcome_kind: str
    constraint_validation_passed: bool
    total_arrivals: float
    total_served: float
    total_unserved: float
    total_allocated_power_kw: float
    avg_utilization_pct: float
    created_at: datetime
