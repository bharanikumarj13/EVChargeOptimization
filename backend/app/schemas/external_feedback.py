from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from app.integrations.station_mapper import StationMapper


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
) -> List[ExternalPhase5FeedbackPayload]:
    """
    Maps local allocation simulation results into EVCharge-Predict Phase 5 feedback contract items.
    Translates internal station IDs ('STN-0X') to canonical predictor IDs ('ST-00X').
    """
    mapped_payloads: List[ExternalPhase5FeedbackPayload] = []

    for res in station_results:
        canonical_station_id = StationMapper.to_external(res.station_id)

        # Distinguish energy (kWh) from power (kW) and vehicle arrivals (integer counts)
        item = ExternalPhase5FeedbackPayload(
            contract_version="1.0",
            allocation_run_id=allocation_run.allocation_id,
            station_id=canonical_station_id,
            interval_start=allocation_run.interval_start,
            interval_end=allocation_run.interval_end,
            allocated_energy_kwh=round(float(res.estimated_served_energy_kwh), 2),
            available_capacity_kw=round(float(res.allocated_power_kw), 2),
            reported_unmet_demand_kwh=round(float(res.estimated_unserved_energy_kwh), 2),
        )
        mapped_payloads.append(item)

    return mapped_payloads
