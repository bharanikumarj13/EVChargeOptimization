import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError
from app.schemas.forecast import ForecastIntervalItem


def test_forecast_interval_item_valid():
    start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    item = ForecastIntervalItem(
        forecast_id="FC-001",
        station_id="STN-01",
        interval_start=start,
        interval_end=end,
        interval_minutes=60,
        predicted_arrivals=10.0,
        predicted_energy_kwh=220.0,
        generated_at=start - timedelta(hours=2),
    )
    assert item.predicted_arrivals == 10.0


def test_forecast_interval_inverted_timestamps():
    start = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)  # inverted
    with pytest.raises(ValidationError):
        ForecastIntervalItem(
            forecast_id="FC-001",
            station_id="STN-01",
            interval_start=start,
            interval_end=end,
            interval_minutes=60,
            predicted_arrivals=10.0,
            predicted_energy_kwh=220.0,
            generated_at=start - timedelta(hours=2),
        )





def test_forecast_interval_negative_arrivals():
    start = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    with pytest.raises(ValidationError):
        ForecastIntervalItem(
            forecast_id="FC-001",
            station_id="STN-01",
            interval_start=start,
            interval_end=end,
            interval_minutes=60,
            predicted_arrivals=-5.0,  # negative
            predicted_energy_kwh=220.0,
            generated_at=start - timedelta(hours=2),
        )


def test_mock_provider_dynamic_adjustment_indexing():
    from app.integrations.mock_provider import MockForecastProvider
    from app.core.exceptions import InvalidForecastError

    provider = MockForecastProvider(base_start_time=datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc))

    # Submit mock feedback
    fb_payload = {
        "feedback_id": "FBD-TEST-DYN",
        "station_outcomes": [
            {
                "station_id": "STN-01",
                "estimated_unserved": 4.0,
                "predicted_arrivals": 10.0,
                "predicted_energy_kwh": 200.0,
            },
            {
                "station_id": "STN-CUSTOM-UNKNOWN",  # Custom unknown station
                "estimated_unserved": 2.0,
                "predicted_arrivals": 5.0,
                "predicted_energy_kwh": 100.0,
            },
        ],
        "deferred_fraction": 0.70,
        "forecast_id": "FC-001",
    }
    provider.submit_feedback(fb_payload)

    # 1. Target interval: 10:00 - 11:00 (index 2 relative to 08:00 start)
    adj = provider.get_next_operational_adjustment(
        feedback_id="FBD-TEST-DYN",
        target_interval_start="2026-10-26T10:00:00Z",
        target_interval_end="2026-10-26T11:00:00Z",
    )
    assert adj is not None
    stn_map = {item["station_id"]: item for item in adj["station_adjustments"]}

    # STN-01 at interval index 2 has base demand (12.0, 260.0) from BASE_DEMAND_MATRIX
    assert stn_map["STN-01"]["original_predicted_arrivals"] == 12.0
    assert stn_map["STN-01"]["original_predicted_energy_kwh"] == 260.0

    # STN-CUSTOM-UNKNOWN handled safely with default fallback (no IndexError)
    assert "STN-CUSTOM-UNKNOWN" in stn_map
    assert stn_map["STN-CUSTOM-UNKNOWN"]["original_predicted_arrivals"] == 10.0
    assert stn_map["STN-CUSTOM-UNKNOWN"]["original_predicted_energy_kwh"] == 200.0

    # 2. Out-of-horizon timestamp raises InvalidForecastError explicitly
    with pytest.raises(InvalidForecastError):
        provider.get_next_operational_adjustment(
            feedback_id="FBD-TEST-DYN",
            target_interval_start="2026-10-26T18:00:00Z",  # Index 10 (> 5)
            target_interval_end="2026-10-26T19:00:00Z",
        )

    # Past out-of-horizon timestamp raises InvalidForecastError
    with pytest.raises(InvalidForecastError):
        provider.get_next_operational_adjustment(
            feedback_id="FBD-TEST-DYN",
            target_interval_start="2026-10-26T06:00:00Z",  # Before 08:00
            target_interval_end="2026-10-26T07:00:00Z",
        )

    # Corrupt timestamp format raises InvalidForecastError
    with pytest.raises(InvalidForecastError):
        provider.get_next_operational_adjustment(
            feedback_id="FBD-TEST-DYN",
            target_interval_start="not-a-valid-timestamp",
            target_interval_end="also-invalid",
        )



