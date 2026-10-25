from typing import List, Dict, Tuple, Optional
from app.models.station import Station
from app.models.grid_group import GridGroup


class ConstraintCheckResult:
    def __init__(self, passed: bool, violations: List[str], warnings: List[str]):
        self.passed = passed
        self.violations = violations
        self.warnings = warnings


def validate_station_config(station: Station) -> Tuple[bool, List[str]]:
    """Validates structural station configuration constraints."""
    errors = []
    if station.charger_count < 1:
        errors.append(f"Station {station.station_id}: charger_count must be at least 1")
    if station.available_chargers < 0:
        errors.append(f"Station {station.station_id}: available_chargers cannot be negative")
    if station.available_chargers > station.charger_count:
        errors.append(
            f"Station {station.station_id}: available_chargers ({station.available_chargers}) "
            f"exceeds installed charger_count ({station.charger_count})"
        )
    if station.charger_power_kw_per_charger <= 0:
        errors.append(f"Station {station.station_id}: charger_power_kw_per_charger must be positive")
    if station.station_power_limit_kw <= 0:
        errors.append(f"Station {station.station_id}: station_power_limit_kw must be positive")
    if station.avg_session_minutes <= 0:
        errors.append(f"Station {station.station_id}: avg_session_minutes must be positive")
    return len(errors) == 0, errors


def validate_allocation_constraints(
    stations: List[Station],
    grid_groups: Dict[str, GridGroup],
    allocations_by_station: Dict[str, Dict[str, float]],
) -> ConstraintCheckResult:
    """
    Validates all mandatory hard constraints for a computed allocation across stations and shared grids:
    - Allocated power cannot be negative.
    - Inactive stations cannot receive power.
    - Station power cannot exceed configured station power limit.
    - Station power cannot exceed charger capacity (available_chargers * charger_power_kw_per_charger).
    - Aggregate allocated power in a grid group cannot exceed residual shared grid capacity.
    """
    violations = []
    warnings = []

    # Map grid group allocations
    grid_allocated_power: Dict[str, float] = {gid: 0.0 for gid in grid_groups}

    for stn in stations:
        stn_alloc = allocations_by_station.get(stn.station_id, {})
        allocated_power = stn_alloc.get("allocated_power_kw", 0.0)

        # Non-negativity check
        if allocated_power < 0:
            violations.append(f"Station {stn.station_id}: allocated power {allocated_power} kW cannot be negative")

        # Inactive station check
        if not stn.is_active and allocated_power > 0.001:
            violations.append(f"Station {stn.station_id} is inactive but received {allocated_power} kW")

        # Station power limit check
        if allocated_power > stn.station_power_limit_kw + 1e-4:
            violations.append(
                f"Station {stn.station_id}: allocated power {allocated_power:.2f} kW "
                f"exceeds station limit {stn.station_power_limit_kw:.2f} kW"
            )

        # Per-charger physical power limit check
        max_charger_power = stn.available_chargers * stn.charger_power_kw_per_charger
        if allocated_power > max_charger_power + 1e-4:
            violations.append(
                f"Station {stn.station_id}: allocated power {allocated_power:.2f} kW "
                f"exceeds available charger capacity {max_charger_power:.2f} kW"
            )

        # Accumulate to shared grid group
        if stn.grid_group_id in grid_allocated_power:
            grid_allocated_power[stn.grid_group_id] += allocated_power
        else:
            violations.append(f"Station {stn.station_id} references unknown grid_group_id '{stn.grid_group_id}'")

    # Grid group capacity constraints
    for gid, group in grid_groups.items():
        residual_cap = group.residual_capacity_kw
        allocated = grid_allocated_power.get(gid, 0.0)
        if allocated > residual_cap + 1e-4:
            violations.append(
                f"Grid Group {gid} ({group.grid_group_name}): aggregate allocated EV power {allocated:.2f} kW "
                f"exceeds residual grid capacity {residual_cap:.2f} kW (limit: {group.grid_limit_kw} kW, other load: {group.other_load_kw} kW)"
            )
        elif residual_cap > 0 and (allocated / residual_cap) > 0.90:
            warnings.append(f"Grid Group {gid} is operating at high load ({(allocated / residual_cap)*100:.1f}%)")

    return ConstraintCheckResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
