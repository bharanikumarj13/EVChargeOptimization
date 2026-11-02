from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Set, Union
from pydantic import BaseModel, Field, model_validator
from app.core.exceptions import InvalidForecastError


class ForecastIntervalRead(BaseModel):
    """External EVCharge-Predict forecast interval prediction matching the OpenAPI contract."""
    model_config = {"protected_namespaces": ()}

    interval_start: datetime
    interval_end: datetime
    predicted_arrivals: Union[int, float] = Field(..., ge=0, description="Predicted arrival count (>= 0)")
    predicted_energy_kwh: float = Field(..., ge=0.0, description="Predicted charging energy requirement in kWh (>= 0)")

    @model_validator(mode="after")
    def validate_timestamps(self):
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("Interval timestamps must be timezone-aware UTC")
        if self.interval_start.utcoffset() != timedelta(0) or self.interval_end.utcoffset() != timedelta(0):
            raise ValueError("Interval timestamps must have UTC timezone (+00:00 or Z)")
        if self.interval_start >= self.interval_end:
            raise ValueError(
                f"interval_start ({self.interval_start}) must be before interval_end ({self.interval_end})"
            )
        return self


class StationForecastRead(BaseModel):
    """External EVCharge-Predict container for a single station's intervals."""
    model_config = {"protected_namespaces": ()}

    station_id: str = Field(..., min_length=1, max_length=64)
    intervals: List[ForecastIntervalRead] = Field(..., min_length=1)


class HorizonMetadata(BaseModel):
    """External EVCharge-Predict horizon parameters."""
    model_config = {"protected_namespaces": ()}

    start: datetime
    end: datetime
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    interval_count: int = Field(default=6, ge=1, le=24)

    @model_validator(mode="after")
    def validate_horizon(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Horizon start and end must be timezone-aware UTC")
        if self.start.utcoffset() != timedelta(0) or self.end.utcoffset() != timedelta(0):
            raise ValueError("Horizon start and end must have UTC timezone (+00:00 or Z)")
        if self.start >= self.end:
            raise ValueError(f"Horizon start ({self.start}) must be before horizon end ({self.end})")
        return self


class ModelProvenanceMetadata(BaseModel):
    """Provenance and metadata of the predictive ML model."""
    model_config = {"protected_namespaces": ()}

    model_version: str = Field(default="1.0", max_length=64)
    training_data_type: str = Field(default="synthetic", max_length=64)
    scikit_learn_version: Optional[str] = None
    training_data_fingerprint: Optional[str] = None


class ForecastDetailRead(BaseModel):
    """External EVCharge-Predict full detail forecast response matching the partner contract."""
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    generated_at: datetime
    horizon: HorizonMetadata
    demand_type: str = Field(default="baseline", max_length=32)
    stations: List[StationForecastRead] = Field(..., min_length=1)
    model: Optional[ModelProvenanceMetadata] = None


class ForecastIntervalItem(BaseModel):
    model_config = {"protected_namespaces": ()}

    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: Optional[str] = Field(None, max_length=128)
    station_id: str = Field(..., min_length=1, max_length=64)
    interval_start: datetime
    interval_end: datetime
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    predicted_arrivals: float = Field(..., ge=0.0, description="Predicted arrival vehicles (>= 0)")
    predicted_energy_kwh: float = Field(..., ge=0.0, description="Predicted charging energy requirement in kWh (>= 0)")
    model_version: str = Field(default="v1.0", max_length=64)
    generated_at: datetime

    @model_validator(mode="after")
    def validate_interval_timestamps(self):
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError(
                f"interval_start ({self.interval_start}) and interval_end ({self.interval_end}) must be timezone-aware UTC"
            )
        if self.interval_start.utcoffset() != timedelta(0) or self.interval_end.utcoffset() != timedelta(0):
            raise ValueError(
                f"interval_start ({self.interval_start}) and interval_end ({self.interval_end}) must have UTC timezone (+00:00 or Z)"
            )
        if self.interval_start >= self.interval_end:
            raise ValueError(
                f"interval_start ({self.interval_start}) must be before interval_end ({self.interval_end})"
            )
        duration_minutes = (self.interval_end - self.interval_start).total_seconds() / 60.0
        if abs(duration_minutes - self.interval_minutes) > 0.01:
            raise ValueError(
                f"Calculated duration {duration_minutes}m does not match interval_minutes ({self.interval_minutes}m)"
            )
        return self


class ForecastResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    forecast_id: str
    scenario_id: Optional[str] = None
    model_version: str
    generated_at: datetime
    intervals: List[ForecastIntervalItem]
    interval_count: int
    station_ids: List[str]


class ForecastCreateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    scenario_id: str = Field(..., min_length=1, max_length=64, description="Scenario identifier")
    station_ids: List[str] = Field(..., min_length=1, description="List of station IDs to forecast")
    forecast_start: datetime = Field(..., description="UTC start datetime for forecast horizon (minute and second must be 0)")
    interval_minutes: int = Field(default=60, description="Duration per interval in minutes (EVCharge-Opt currently requires 60m)")
    horizon_intervals: int = Field(default=6, description="Number of intervals in the planning horizon (EVCharge-Opt currently requires 6)")

    @model_validator(mode="after")
    def validate_request_parameters(self):
        cleaned_stations = [s.strip() for s in self.station_ids if s and s.strip()]
        if not cleaned_stations:
            raise ValueError("station_ids must contain at least one non-empty station identifier")
        if len(cleaned_stations) != len(set(cleaned_stations)):
            raise ValueError("station_ids contains duplicate station identifiers")
        self.station_ids = cleaned_stations

        # Normalize UTC if naive
        if self.forecast_start.tzinfo is None:
            self.forecast_start = self.forecast_start.replace(tzinfo=timezone.utc)

        # forecast_start hourly alignment
        if self.forecast_start.minute != 0 or self.forecast_start.second != 0 or self.forecast_start.microsecond != 0:
            raise ValueError("forecast_start must be aligned to the top of the hour (minute=0, second=0)")

        # Section 4: Initially support exactly six consecutive hourly intervals. Reject unsupported intervals and horizons.
        if self.interval_minutes != 60:
            raise ValueError(
                f"Unsupported interval_minutes: {self.interval_minutes}. EVCharge-Opt initial integration requires 60-minute intervals."
            )
        if self.horizon_intervals != 6:
            raise ValueError(
                f"Unsupported horizon_intervals: {self.horizon_intervals}. EVCharge-Opt initial integration requires exactly 6 planning intervals."
            )

        return self


class ForecastAcknowledgement(BaseModel):
    model_config = {"protected_namespaces": ()}

    contract_version: str = Field(default="1.0", max_length=16)
    forecast_id: str = Field(..., min_length=1, max_length=64)
    scenario_id: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="generated", max_length=32)
    demand_type: str = Field(default="baseline", max_length=32)
    generated_at: datetime
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    horizon_intervals: int = Field(default=6, ge=1, le=24)
    forecast_url: str = Field(..., max_length=256)


def validate_forecast_horizon_integrity(
    intervals: List[ForecastIntervalItem],
    expected_horizon_intervals: int = 6,
    expected_interval_minutes: int = 60,
    expected_station_ids: Optional[List[str]] = None,
) -> None:
    """
    Validates that forecast intervals form a valid, non-overlapping, chronological horizon
    with consecutive hourly intervals for each station.
    Verifies:
    - Exactly expected_horizon_intervals per requested station
    - UTC-aware timestamps and correct interval boundaries
    - Consecutive non-overlapping intervals (no gaps, no overlaps)
    - No duplicate station-interval records
    - No unexpected or missing stations
    - Finite, non-negative arrival and energy predictions
    """
    if not intervals:
        raise InvalidForecastError("Forecast intervals list is empty.")

    by_station: Dict[str, List[ForecastIntervalItem]] = {}
    seen_station_intervals: Set[str] = set()

    for it in intervals:
        # UTC awareness check
        if it.interval_start.tzinfo is None or it.interval_end.tzinfo is None:
            raise InvalidForecastError(
                f"Interval timestamps for station '{it.station_id}' must be timezone-aware UTC."
            )
        if it.interval_start.utcoffset() != timedelta(0) or it.interval_end.utcoffset() != timedelta(0):
            raise InvalidForecastError(
                f"Interval timestamps for station '{it.station_id}' must have UTC timezone (+00:00 or Z)."
            )

        # Check non-negative and finite
        if it.predicted_arrivals < 0 or it.predicted_energy_kwh < 0:
            raise InvalidForecastError(
                f"Negative forecast values for station '{it.station_id}': arrivals={it.predicted_arrivals}, energy={it.predicted_energy_kwh}."
            )

        # Hourly alignment check if 60-minute interval
        if expected_interval_minutes == 60:
            if it.interval_start.minute != 0 or it.interval_start.second != 0 or it.interval_start.microsecond != 0:
                raise InvalidForecastError(
                    f"Interval start ({it.interval_start.isoformat()}) for station '{it.station_id}' must be aligned to top of the hour."
                )

        # Check duplicate station-interval records
        key = f"{it.station_id}_{it.interval_start.isoformat()}"
        if key in seen_station_intervals:
            raise InvalidForecastError(
                f"Duplicate forecast interval found for station '{it.station_id}' at start '{it.interval_start.isoformat()}'."
            )
        seen_station_intervals.add(key)

        by_station.setdefault(it.station_id, []).append(it)

    if expected_station_ids:
        missing_stations = set(expected_station_ids) - set(by_station.keys())
        if missing_stations:
            raise InvalidForecastError(
                f"Forecast is missing intervals for expected station(s): {sorted(list(missing_stations))}",
                validation_errors=[{"missing_stations": sorted(list(missing_stations))}],
            )
        unexpected_stations = set(by_station.keys()) - set(expected_station_ids)
        if unexpected_stations:
            raise InvalidForecastError(
                f"Forecast contains unexpected station(s) outside expected set: {sorted(list(unexpected_stations))}",
                validation_errors=[{"unexpected_stations": sorted(list(unexpected_stations))}],
            )

    for stn_id, stn_intervals in by_station.items():
        if len(stn_intervals) != expected_horizon_intervals:
            raise InvalidForecastError(
                f"Station '{stn_id}' has {len(stn_intervals)} intervals, expected exactly {expected_horizon_intervals}.",
                validation_errors=[{"station_id": stn_id, "interval_count": len(stn_intervals)}],
            )

        # Sort intervals chronologically
        sorted_intervals = sorted(stn_intervals, key=lambda x: x.interval_start)

        for idx, item in enumerate(sorted_intervals):
            duration_minutes = (item.interval_end - item.interval_start).total_seconds() / 60.0
            if abs(duration_minutes - expected_interval_minutes) > 0.01:
                raise InvalidForecastError(
                    f"Interval {idx} for station '{stn_id}' duration is {duration_minutes}m, expected {expected_interval_minutes}m."
                )

            if idx > 0:
                prev_end = sorted_intervals[idx - 1].interval_end
                curr_start = item.interval_start
                if prev_end != curr_start:
                    raise InvalidForecastError(
                        f"Non-consecutive or overlapping intervals for station '{stn_id}' at index {idx}: "
                        f"previous end {prev_end.isoformat()} != current start {curr_start.isoformat()}."
                    )
