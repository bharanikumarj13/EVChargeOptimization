import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.schemas.external_feedback import map_allocation_to_external_phase5, ExternalPhase5FeedbackPayload


def test_map_allocation_to_external_phase5():
    mock_run = MagicMock()
    mock_run.allocation_id = "ALC-12345"
    mock_run.interval_start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    mock_run.interval_end = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)

    mock_res_1 = MagicMock()
    mock_res_1.station_id = "STN-01"
    mock_res_1.estimated_served_energy_kwh = 280.5
    mock_res_1.allocated_power_kw = 350.0
    mock_res_1.estimated_unserved_energy_kwh = 45.2

    mock_res_2 = MagicMock()
    mock_res_2.station_id = "STN-02"
    mock_res_2.estimated_served_energy_kwh = 190.0
    mock_res_2.allocated_power_kw = 200.0
    mock_res_2.estimated_unserved_energy_kwh = 0.0

    payloads = map_allocation_to_external_phase5(mock_run, [mock_res_1, mock_res_2])

    assert len(payloads) == 2

    # Check station 1 mapping
    p1 = payloads[0]
    assert p1.contract_version == "1.0"
    assert p1.allocation_run_id == "ALC-12345"
    assert p1.station_id == "ST-001"  # Mapped from STN-01 to canonical external ST-001
    assert p1.allocated_energy_kwh == 280.5
    assert p1.available_capacity_kw == 350.0
    assert p1.reported_unmet_demand_kwh == 45.2

    # Check station 2 mapping
    p2 = payloads[1]
    assert p2.station_id == "ST-002"  # Mapped from STN-02 to canonical external ST-002
    assert p2.allocated_energy_kwh == 190.0
    assert p2.available_capacity_kw == 200.0
    assert p2.reported_unmet_demand_kwh == 0.0
