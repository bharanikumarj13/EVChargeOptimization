from typing import Dict, Any, Optional


def calculate_waiting_time(
    eligible_arrivals: float,
    station_vehicle_capacity: float,
    avg_session_minutes: float,
) -> float:
    """
    Transparent queue delay estimation (minutes).
    Uses a bounded M/M/c-style delay approximation when within capacity,
    and linear backlog accumulation when arrivals exceed physical station turnover.
    """
    if eligible_arrivals <= 0 or station_vehicle_capacity <= 0:
        return 0.0

    load_ratio = eligible_arrivals / station_vehicle_capacity

    if load_ratio <= 1.0:
        # Standard queuing delay under non-saturated conditions
        # Expected wait increases non-linearly with load ratio
        wait = (avg_session_minutes / 2.0) * (load_ratio ** 2)
    else:
        # Saturated queue: base delay plus wait time for unserved backlog
        overflow_ratio = load_ratio - 1.0
        wait = (avg_session_minutes * 0.5) + (overflow_ratio * avg_session_minutes * 1.5)

    return round(min(wait, 180.0), 1)  # Capped at 3 hours for operational realism


def calculate_utilization(
    estimated_served: float,
    avg_session_minutes: float,
    available_chargers: int,
    interval_minutes: int = 60,
) -> float:
    """
    Calculates charger time utilization percentage:
    utilization = (occupied_charger_minutes / available_charger_minutes) * 100
    """
    if available_chargers <= 0 or interval_minutes <= 0:
        return 0.0

    occupied_minutes = estimated_served * avg_session_minutes
    available_minutes = available_chargers * interval_minutes
    util_pct = (occupied_minutes / available_minutes) * 100.0
    return round(min(100.0, max(0.0, util_pct)), 1)


def calculate_deferred_demand(
    unserved_vehicles: float,
    unserved_energy_kwh: float,
    deferred_fraction: float = 0.70,
) -> Dict[str, float]:
    """
    Calculates operational deferred demand assumptions for the next interval.
    """
    fraction = max(0.0, min(1.0, deferred_fraction))
    deferred_veh = round(unserved_vehicles * fraction, 1)
    deferred_kwh = round(unserved_energy_kwh * fraction, 1)
    return {
        "deferred_fraction": fraction,
        "deferred_vehicles": deferred_veh,
        "deferred_energy_kwh": deferred_kwh,
    }
