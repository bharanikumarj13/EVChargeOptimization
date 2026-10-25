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
