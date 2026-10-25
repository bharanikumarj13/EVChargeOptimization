"""
Seed script to populate initial stations, grid groups, and sample scenario for EVCharge-Opt.
Usage: python backend/scripts/seed_data.py
"""
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.grid_group import GridGroup
from app.models.station import Station
from app.models.scenario import Scenario


def seed():
    db = SessionLocal()
    try:
        print("🌱 Seeding Grid Groups...")
        grid_groups = [
            GridGroup(
                grid_group_id="GRID-METRO",
                grid_group_name="Metro Central Shared Substation",
                grid_limit_kw=750.0,
                other_load_kw=150.0,
            ),
            GridGroup(
                grid_group_id="GRID-SUBURB",
                grid_group_name="Suburban Feeder Substation",
                grid_limit_kw=400.0,
                other_load_kw=50.0,
            ),
            GridGroup(
                grid_group_id="GRID-HIGHWAY",
                grid_group_name="Interstate Highway High-Voltage Hub",
                grid_limit_kw=800.0,
                other_load_kw=100.0,
            ),
        ]
        for g in grid_groups:
            existing = db.query(GridGroup).filter(GridGroup.grid_group_id == g.grid_group_id).first()
            if not existing:
                db.add(g)
        db.commit()

        print("🌱 Seeding Stations...")
        stations = [
            Station(
                station_id="STN-01",
                station_name="Downtown Fast Charging Hub",
                charger_count=8,
                available_chargers=8,
                charger_power_kw_per_charger=50.0,
                station_power_limit_kw=350.0,
                avg_session_minutes=40.0,
                grid_group_id="GRID-METRO",
                is_active=True,
            ),
            Station(
                station_id="STN-02",
                station_name="Tech Park Workplace Station",
                charger_count=12,
                available_chargers=10,
                charger_power_kw_per_charger=22.0,
                station_power_limit_kw=240.0,
                avg_session_minutes=60.0,
                grid_group_id="GRID-METRO",
                is_active=True,
            ),
            Station(
                station_id="STN-03",
                station_name="Suburban Retail Plaza",
                charger_count=6,
                available_chargers=6,
                charger_power_kw_per_charger=50.0,
                station_power_limit_kw=250.0,
                avg_session_minutes=45.0,
                grid_group_id="GRID-SUBURB",
                is_active=True,
            ),
            Station(
                station_id="STN-04",
                station_name="Highway Transit Depot",
                charger_count=4,
                available_chargers=4,
                charger_power_kw_per_charger=150.0,
                station_power_limit_kw=500.0,
                avg_session_minutes=25.0,
                grid_group_id="GRID-HIGHWAY",
                is_active=True,
            ),
            Station(
                station_id="STN-05",
                station_name="University Campus Station",
                charger_count=6,
                available_chargers=5,
                charger_power_kw_per_charger=22.0,
                station_power_limit_kw=120.0,
                avg_session_minutes=50.0,
                grid_group_id="GRID-METRO",
                is_active=True,
            ),
        ]
        for s in stations:
            existing = db.query(Station).filter(Station.station_id == s.station_id).first()
            if not existing:
                db.add(s)
        db.commit()

        print("🌱 Seeding Baseline Scenario...")
        sample_scenario = Scenario(
            scenario_id="SCN-001",
            name="Metro Morning Peak Horizon",
            description="Operational allocation run under peak weekday commuting demand",
            selected_forecast_id="FC-001",
            planning_horizon_intervals=6,
            provider_mode="mock",
        )
        existing_scn = db.query(Scenario).filter(Scenario.scenario_id == sample_scenario.scenario_id).first()
        if not existing_scn:
            db.add(sample_scenario)
            db.commit()

        print("✅ Database seeding complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
