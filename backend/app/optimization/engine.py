from typing import List, Dict, Any, Tuple
from app.models.station import Station
from app.models.grid_group import GridGroup
from app.optimization.constraints import validate_allocation_constraints, ConstraintCheckResult
from app.simulation.impact import calculate_waiting_time, calculate_utilization


class AllocationEngine:
    """
    Deterministic, explainable constraint-aware EV charging allocation engine.
    Satisfies hard station and shared grid limits, maximizes feasible demand served,
    and calculates operational impact metrics.
    """

    ALGORITHM_VERSION = "v1.0-priority-heuristic"
    OBJECTIVE_DESCRIPTION = (
        "Hierarchical priority optimization: (1) Maximize feasible served EV arrivals; "
        "(2) Satisfy physical charger and station power ratings; "
        "(3) Respect shared residual grid limits; (4) Minimize unserved demand and wait times."
    )

    @classmethod
    def optimize(
        cls,
        stations: List[Station],
        grid_groups: Dict[str, GridGroup],
        demand_by_station: Dict[str, Dict[str, float]],
        interval_minutes: int = 60,
    ) -> Tuple[bool, str, List[Dict[str, Any]], List[str]]:
        """
        Executes the optimization algorithm.
        Returns:
            passed (bool): Whether all hard constraints were satisfied.
            status (str): "success", "infeasible", or "partial".
            results (List[Dict]): Station-wise allocation and simulation results.
            warnings (List[str]): Any operational or grid warnings.
        """
        interval_hours = interval_minutes / 60.0
        station_allocations: Dict[str, Dict[str, float]] = {}

        # 1. Group active stations by grid group
        grid_station_map: Dict[str, List[Station]] = {gid: [] for gid in grid_groups}
        for stn in stations:
            if stn.grid_group_id in grid_station_map:
                grid_station_map[stn.grid_group_id].append(stn)

        # 2. Compute power demands per station respecting individual station caps
        provisional_power: Dict[str, float] = {}
        for stn in stations:
            if not stn.is_active or stn.available_chargers == 0:
                provisional_power[stn.station_id] = 0.0
                continue

            station_demand = demand_by_station.get(stn.station_id, {})
            energy_kwh = station_demand.get("predicted_energy_kwh", 0.0)

            # Max power station hardware can accept
            charger_cap_kw = stn.available_chargers * stn.charger_power_kw_per_charger
            physical_station_kw = min(stn.station_power_limit_kw, charger_cap_kw)

            # Power needed to deliver requested energy in interval
            required_power_kw = (energy_kwh / interval_hours) if interval_hours > 0 else 0.0
            provisional_power[stn.station_id] = min(physical_station_kw, required_power_kw)

        # 3. Enforce shared grid group residual capacity
        final_allocated_power: Dict[str, float] = {}
        grid_warnings: List[str] = []

        for gid, group in grid_groups.items():
            residual_kw = group.residual_capacity_kw
            group_stations = [s for s in grid_station_map.get(gid, []) if s.is_active]
            total_group_demanded = sum(provisional_power.get(s.station_id, 0.0) for s in group_stations)

            if total_group_demanded <= residual_kw:
                for s in group_stations:
                    final_allocated_power[s.station_id] = round(provisional_power.get(s.station_id, 0.0), 2)
            else:
                # Grid congestion: Proportional curtailment while prioritizing active demand
                grid_warnings.append(
                    f"Grid Group '{group.grid_group_name}' ({gid}) congested: demand {total_group_demanded:.1f} kW "
                    f"exceeds residual capacity {residual_kw:.1f} kW. Power proportionally allocated."
                )
                ratio = residual_kw / total_group_demanded if total_group_demanded > 0 else 0.0
                for s in group_stations:
                    final_allocated_power[s.station_id] = round(provisional_power.get(s.station_id, 0.0) * ratio, 2)

        # Ensure inactive stations get 0.0
        for stn in stations:
            if not stn.is_active:
                final_allocated_power[stn.station_id] = 0.0

        # 4. Impact Simulation (served vehicles, energy, waiting time, utilization)
        results: List[Dict[str, Any]] = []

        for stn in stations:
            station_demand = demand_by_station.get(stn.station_id, {})
            arrivals = station_demand.get("predicted_arrivals", 0.0)
            energy_kwh = station_demand.get("predicted_energy_kwh", 0.0)
            alloc_power = final_allocated_power.get(stn.station_id, 0.0)

            stn_warnings: List[str] = []

            if not stn.is_active:
                stn_warnings.append("Station is currently inactive; zero power allocated.")
                results.append({
                    "station_id": stn.station_id,
                    "station_name": stn.station_name,
                    "predicted_arrivals": arrivals,
                    "predicted_energy_kwh": energy_kwh,
                    "estimated_served": 0.0,
                    "estimated_unserved": arrivals,
                    "allocated_power_kw": 0.0,
                    "estimated_served_energy_kwh": 0.0,
                    "estimated_unserved_energy_kwh": energy_kwh,
                    "estimated_wait_minutes": None,
                    "charger_utilization_pct": 0.0,
                    "warnings": stn_warnings,
                })
                station_allocations[stn.station_id] = {"allocated_power_kw": 0.0}
                continue

            # Physical turnover capacity
            session_mins = max(stn.avg_session_minutes, 1.0)
            turnover_per_charger = 60.0 / session_mins
            max_phys_capacity = stn.available_chargers * turnover_per_charger

            # Energy delivery capacity under allocated power
            delivered_energy_capacity = alloc_power * interval_hours
            if arrivals > 0 and energy_kwh > 0:
                avg_kwh_per_veh = energy_kwh / arrivals
                energy_vehicle_capacity = delivered_energy_capacity / avg_kwh_per_veh
            else:
                energy_vehicle_capacity = max_phys_capacity

            # Feasible served is minimum of arrivals, physical turnover, and energy allowance
            feasible_served = min(arrivals, max_phys_capacity, energy_vehicle_capacity)
            feasible_served = round(max(0.0, feasible_served), 1)

            unserved = round(max(0.0, arrivals - feasible_served), 1)
            # Guarantee conservation of arrivals
            if round(feasible_served + unserved, 1) != round(arrivals, 1):
                unserved = round(arrivals - feasible_served, 1)

            # Served energy calculation
            if arrivals > 0:
                served_ratio = feasible_served / arrivals
                served_energy = round(min(energy_kwh, energy_kwh * served_ratio), 1)
                unserved_energy = round(max(0.0, energy_kwh - served_energy), 1)
            else:
                served_energy = 0.0
                unserved_energy = 0.0

            # Waiting time estimation
            wait_time = calculate_waiting_time(arrivals, max_phys_capacity, session_mins)

            # Charger utilization
            util_pct = calculate_utilization(feasible_served, session_mins, stn.available_chargers, interval_minutes)

            if unserved > 0:
                stn_warnings.append(f"{unserved} predicted vehicles cannot be served during this interval.")

            results.append({
                "station_id": stn.station_id,
                "station_name": stn.station_name,
                "predicted_arrivals": arrivals,
                "predicted_energy_kwh": energy_kwh,
                "estimated_served": feasible_served,
                "estimated_unserved": unserved,
                "allocated_power_kw": alloc_power,
                "estimated_served_energy_kwh": served_energy,
                "estimated_unserved_energy_kwh": unserved_energy,
                "estimated_wait_minutes": wait_time,
                "charger_utilization_pct": util_pct,
                "warnings": stn_warnings,
            })
            station_allocations[stn.station_id] = {"allocated_power_kw": alloc_power}

        # 5. Hard Constraint Validation
        validation = validate_allocation_constraints(stations, grid_groups, station_allocations)
        all_warnings = grid_warnings + validation.warnings

        if not validation.passed:
            return False, "infeasible", results, validation.violations + all_warnings

        status = "success"
        return True, status, results, all_warnings
