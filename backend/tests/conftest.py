import os
import sys

# Ensure backend root is on Python sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.grid_group import GridGroup
from app.models.station import Station
from app.models.scenario import Scenario

# SQLite in-memory database with StaticPool so all connections share the memory DB
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Creates a fresh in-memory database schema for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        # Populate standard test fixture grid groups and stations
        gg1 = GridGroup(
            grid_group_id="GRID-METRO",
            grid_group_name="Metro Grid",
            grid_limit_kw=600.0,
            other_load_kw=100.0,
        )
        gg2 = GridGroup(
            grid_group_id="GRID-SUBURB",
            grid_group_name="Suburb Grid",
            grid_limit_kw=400.0,
            other_load_kw=50.0,
        )
        session.add_all([gg1, gg2])
        session.commit()

        stn1 = Station(
            station_id="STN-01",
            station_name="Downtown Fast Hub",
            charger_count=8,
            available_chargers=8,
            charger_power_kw_per_charger=50.0,
            station_power_limit_kw=350.0,
            avg_session_minutes=40.0,
            grid_group_id="GRID-METRO",
            is_active=True,
        )
        stn2 = Station(
            station_id="STN-02",
            station_name="Tech Park Workplace",
            charger_count=10,
            available_chargers=8,
            charger_power_kw_per_charger=22.0,
            station_power_limit_kw=200.0,
            avg_session_minutes=60.0,
            grid_group_id="GRID-METRO",
            is_active=True,
        )
        session.add_all([stn1, stn2])
        session.commit()

        scn = Scenario(
            scenario_id="SCN-TEST-01",
            name="Test Horizon Scenario",
            selected_forecast_id="FC-001",
            planning_horizon_intervals=6,
            provider_mode="mock",
        )
        session.add(scn)
        session.commit()

        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Provides a TestClient with database session overridden."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
