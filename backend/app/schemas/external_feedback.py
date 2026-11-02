from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Union, Dict
from pydantic import BaseModel, Field, model_validator


class AllocationIntervalInput(BaseModel):
    """Interval-level allocation result reported by EVCharge-Opt matching the OpenAPI contract."""
    model_config = {"protected_namespaces": ()}

    interval_start: datetime
    interval_end: datetime
    allocated_energy_kwh: Optional[float] = Field(None, ge=0.0, description="Energy allocated by optimizer (kWh)")
    available_capacity_kw: Optional[float] = Field(None, ge=0.0, description="Available charger capacity (kW)")
    reported_unmet_demand_kwh: Optional[float] = Field(None, ge=0.0, description="Unmet energy demand reported by optimizer (kWh)")

    @model_validator(mode="after")
    def validate_utc_timestamps(self):
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("Interval timestamps must be timezone-aware UTC")
        if self.interval_start.utcoffset() != timedelta(0) or self.interval_end.utcoffset() != timedelta(0):
            raise ValueError("Interval timestamps must have UTC timezone (+00:00 or Z)")
        if self.interval_start >= self.interval_end:
            raise ValueError(
                f"interval_start ({self.interval_start}) must be before interval_end ({self.interval_end})"
            )
        return self


class StationAllocationFeedbackInput(BaseModel):
    """Station-level allocation feedback with consecutive hourly intervals."""
    model_config = {"protected_namespaces": ()}

    station_id: str = Field(..., min_length=1, max_length=64, description="Canonical station ID (e.g. 'ST-001')")
    intervals: List[AllocationIntervalInput] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_station_intervals(self):
        if not self.intervals:
            raise ValueError(f"Station '{self.station_id}' must contain at least one feedback interval.")
        sorted_invs = sorted(self.intervals, key=lambda x: x.interval_start)
        for idx in range(1, len(sorted_invs)):
            prev = sorted_invs[idx - 1]
            curr = sorted_invs[idx]
            if prev.interval_end != curr.interval_start:
                raise ValueError(
                    f"Station '{self.station_id}' intervals are not consecutive: {prev.interval_end} != {curr.interval_start}"
                )
        return self


class PredictorFeedbackCreateRequest(BaseModel):
    """Payload submitted by EVCharge-Opt to report allocation feedback to EVCharge-Predict."""
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    allocation_run_id: str = Field(..., min_length=1, max_length=128)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    submitted_at: datetime
    optimizer_version: Optional[str] = Field(default="opt-core-1.0", max_length=64)
    stations: List[StationAllocationFeedbackInput] = Field(..., min_length=1)


class PredictorFeedbackCreateResponse(BaseModel):
    """Acknowledgement returned upon feedback submission (HTTP 201 or 200)."""
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    feedback_id: str = Field(..., min_length=1, max_length=64)
    allocation_run_id: str = Field(..., min_length=1, max_length=128)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    status: str = Field(..., max_length=32)
    is_duplicate: bool
    received_at: datetime
    feedback_url: str = Field(..., max_length=256)


class PredictorFeedbackDetailRead(BaseModel):
    """Stored feedback metadata and processing status."""
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    feedback_id: str = Field(..., min_length=1, max_length=64)
    allocation_run_id: str = Field(..., min_length=1, max_length=128)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    status: str = Field(..., max_length=32)
    optimizer_version: Optional[str] = None
    submitted_at: datetime
    received_at: datetime


class AdjustedDemandIntervalRead(BaseModel):
    """Single interval comparing baseline predictions with feedback and derived operational demand."""
    model_config = {"protected_namespaces": ()}

    interval_start: datetime
    interval_end: datetime
    baseline_arrivals: Union[int, float] = Field(..., ge=0)
    baseline_energy_kwh: float = Field(..., ge=0.0)
    allocated_energy_kwh: Optional[float] = Field(None, ge=0.0)
    available_capacity_kw: Optional[float] = Field(None, ge=0.0)
    reported_unmet_demand_kwh: Optional[float] = Field(None, ge=0.0)
    adjusted_operational_demand_kwh: float = Field(..., ge=0.0)
    adjustment_status: str = Field(default="unchanged")

    @model_validator(mode="after")
    def validate_utc_timestamps(self):
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("Interval timestamps must be timezone-aware UTC")
        if self.interval_start.utcoffset() != timedelta(0) or self.interval_end.utcoffset() != timedelta(0):
            raise ValueError("Interval timestamps must have UTC timezone (+00:00 or Z)")
        return self


class StationAdjustedDemandRead(BaseModel):
    """Station container for adjusted demand intervals."""
    model_config = {"protected_namespaces": ()}

    station_id: str = Field(..., min_length=1, max_length=64)
    intervals: List[AdjustedDemandIntervalRead] = Field(..., min_length=1)


class AdjustedDemandResponse(BaseModel):
    """Full feedback-adjusted operational demand payload matching partner contract."""
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    feedback_id: str = Field(..., min_length=1, max_length=64)
    allocation_run_id: str = Field(..., min_length=1, max_length=128)
    demand_type: str = Field(default="feedback-adjusted-operational")
    adjustment_policy_version: str = Field(default="v1-heuristic-operational-envelope")
    policy_description: str
    policy_limitations: str
    computed_at: datetime
    stations: List[StationAdjustedDemandRead] = Field(..., min_length=1)


class ExternalPhase5FeedbackPayload(BaseModel):
    """
    Contract schema expected by EVCharge-Predict for Phase 5 operational feedback.
    Maintains strict separation between arrival vehicle counts, energy (kWh), and power (kW).
    """
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    allocation_run_id: str = Field(..., min_length=1, max_length=64)
    station_id: str = Field(..., min_length=1, max_length=64, description="Canonical predictor station ID (e.g. 'ST-001')")
    interval_start: datetime
    interval_end: datetime
    allocated_energy_kwh: float = Field(..., ge=0.0, description="Total energy allocated/served in kWh")
    available_capacity_kw: float = Field(..., ge=0.0, description="Active power capacity provided in kW")
    reported_unmet_demand_kwh: float = Field(..., ge=0.0, description="Unmet energy demand in kWh")


def map_allocation_to_external_phase5(
    allocation_run: Any,
    station_results: List[Any],
    station_capacities: Optional[Dict[str, float]] = None,
) -> List[ExternalPhase5FeedbackPayload]:
    """
    Maps local allocation simulation results into EVCharge-Predict Phase 5 feedback contract items.
    Translates internal station IDs ('STN-0X') to canonical predictor IDs ('ST-00X').
    """
    from app.integrations.station_mapper import StationMapper

    mapped_payloads: List[ExternalPhase5FeedbackPayload] = []

    for res in station_results:
        canonical_station_id = StationMapper.to_external(res.station_id)

        # Determine station available capacity: check explicitly passed capacity, result attribute, or fallback
        if station_capacities and res.station_id in station_capacities:
            cap_kw = station_capacities[res.station_id]
        elif hasattr(res, "station_capacity_kw") and type(res.station_capacity_kw) in (int, float):
            cap_kw = res.station_capacity_kw
        elif hasattr(res, "available_capacity_kw") and type(res.available_capacity_kw) in (int, float):
            cap_kw = res.available_capacity_kw
        else:
            cap_kw = res.allocated_power_kw

        # Distinguish energy (kWh) from power (kW) and vehicle arrivals (integer counts)
        item = ExternalPhase5FeedbackPayload(
            contract_version="1.0",
            allocation_run_id=allocation_run.allocation_id,
            station_id=canonical_station_id,
            interval_start=allocation_run.interval_start,
            interval_end=allocation_run.interval_end,
            allocated_energy_kwh=round(float(res.estimated_served_energy_kwh), 2),
            available_capacity_kw=round(float(cap_kw), 2),
            reported_unmet_demand_kwh=round(float(res.estimated_unserved_energy_kwh), 2),
        )
        mapped_payloads.append(item)

    return mapped_payloads
