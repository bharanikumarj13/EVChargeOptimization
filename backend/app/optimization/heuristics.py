"""
Operational Planning Heuristics module.

Preserves the semantic boundary between physical simulation metrics,
observed operational outcomes, and partner planning heuristics.
"""
from typing import Dict, Any


def calculate_partner_heuristic_operational_demand(
    baseline_energy_kwh: float,
    allocated_energy_kwh: float,
) -> float:
    """
    Calculates operational planning demand using the partner's documented heuristic:
    adjusted_operational_demand_kwh = max(baseline_energy_kwh, allocated_energy_kwh)

    CRITICAL SEMANTIC GUARANTEES:
    1. This value represents an operational planning heuristic, NOT actual measured demand.
    2. Does NOT substitute or alter arrival counts (predicted_arrivals).
    3. Does NOT alter or overwrite baseline energy predictions (predicted_energy_kwh).
    4. Must be stored and presented distinctly from physical simulation outcomes.
    """
    if baseline_energy_kwh < 0 or allocated_energy_kwh < 0:
        raise ValueError(
            f"Energy quantities must be non-negative: baseline={baseline_energy_kwh}, allocated={allocated_energy_kwh}"
        )
    return round(max(float(baseline_energy_kwh), float(allocated_energy_kwh)), 2)


def validate_energy_power_vehicle_semantics(
    predicted_arrivals: float,
    predicted_energy_kwh: float,
    allocated_power_kw: float,
    allocated_energy_kwh: float,
) -> Dict[str, Any]:
    """
    Verifies that vehicle arrivals (integer/float count), power capacity (kW),
    and energy metrics (kWh) maintain their dimensional distinction without conflation.
    """
    if predicted_arrivals < 0:
        raise ValueError(f"predicted_arrivals cannot be negative: {predicted_arrivals}")
    if predicted_energy_kwh < 0:
        raise ValueError(f"predicted_energy_kwh cannot be negative: {predicted_energy_kwh}")
    if allocated_power_kw < 0:
        raise ValueError(f"allocated_power_kw cannot be negative: {allocated_power_kw}")
    if allocated_energy_kwh < 0:
        raise ValueError(f"allocated_energy_kwh cannot be negative: {allocated_energy_kwh}")

    return {
        "arrival_sessions_count": predicted_arrivals,
        "baseline_energy_demand_kwh": predicted_energy_kwh,
        "active_power_allocation_kw": allocated_power_kw,
        "served_energy_delivered_kwh": allocated_energy_kwh,
        "units": {
            "arrivals": "vehicle_sessions",
            "predicted_energy": "kWh",
            "allocated_power": "kW",
            "allocated_energy": "kWh",
        },
    }
