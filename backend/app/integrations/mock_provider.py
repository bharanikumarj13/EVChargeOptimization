import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from app.integrations.base import ForecastProviderAdapter
from app.schemas.forecast import ForecastIntervalItem, ForecastResponse, ForecastCreateRequest, ForecastAcknowledgement
from app.integrations.station_mapper import StationMapper
from app.core.exceptions import EntityNotFoundError, InvalidForecastError, StationMappingError


class MockForecastProvider(ForecastProviderAdapter):
    """
    Deterministic offline forecast provider that generates realistic 6-interval demand forecasts
    and calculates operational feedback adjustments without external network dependencies.
    """

    MOCK_STATIONS = ["STN-01", "STN-02", "STN-03", "STN-04", "STN-05"]

    # Base profile for arrival and kWh demand by station and interval index (0 to 5)
    # [STN-01: high urban demand, STN-02: workplace morning peak, STN-03: retail midday, STN-04: highway, STN-05: campus]
    BASE_DEMAND_MATRIX = {
        "STN-01": [
            (10.0, 220.0), (14.0, 310.0), (12.0, 260.0), (11.0, 240.0), (15.0, 330.0), (13.0, 290.0)
        ],
        "STN-02": [
            (16.0, 250.0), (22.0, 360.0), (14.0, 210.0), (8.0, 120.0), (7.0, 110.0), (6.0, 95.0)
        ],
        "STN-03": [
            (4.0, 80.0), (6.0, 130.0), (9.0, 190.0), (12.0, 260.0), (14.0, 300.0), (11.0, 240.0)
        ],
        "STN-04": [
            (5.0, 280.0), (7.0, 410.0), (8.0, 480.0), (6.0, 360.0), (8.0, 470.0), (9.0, 520.0)
        ],
        "STN-05": [
            (6.0, 90.0), (10.0, 150.0), (8.0, 120.0), (5.0, 75.0), (7.0, 110.0), (6.0, 95.0)
        ],
    }

    def __init__(self, base_start_time: Optional[datetime] = None):
        if base_start_time is None:
            self.base_start_time = datetime(2026, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
        else:
            self.base_start_time = base_start_time
        self._last_successful_request: Optional[str] = None
        self._submitted_feedback: Dict[str, Dict[str, Any]] = {}
        self._created_forecasts: Dict[str, ForecastResponse] = {}

    def create_forecast(self, req: ForecastCreateRequest) -> ForecastAcknowledgement:
        """
        Creates a deterministic baseline forecast for requested stations and horizon,
        storing it for immediate subsequent retrieval via get_forecast.
        """
        now = datetime.now(timezone.utc)
        forecast_id = f"FC-MOCK-{uuid.uuid4().hex[:6].upper()}"

        active_stations = StationMapper.get_profile_stations()

        # Validate all requested stations against profile and mapping
        mapped_stations = []
        for station_id in req.station_ids:
            try:
                int_stn = StationMapper.to_internal(station_id)
            except Exception as e:
                raise StationMappingError(
                    f"Station '{station_id}' is not mapped to any known internal station.",
                    station_id=station_id,
                ) from e
            if int_stn not in active_stations:
                raise StationMappingError(
                    f"Station '{station_id}' (internal: '{int_stn}') is not supported under active profile "
                    f"'{StationMapper.get_profile()}'. Supported stations: {active_stations}",
                    station_id=station_id,
                )
            mapped_stations.append((station_id, int_stn))

        intervals: List[ForecastIntervalItem] = []
        gen_time = req.forecast_start - timedelta(hours=1)

        # Standard station fallback profiles
        default_profile = [(10.0, 200.0), (14.0, 280.0), (12.0, 240.0), (11.0, 220.0), (15.0, 310.0), (13.0, 270.0)]

        for interval_idx in range(req.horizon_intervals):
            int_start = req.forecast_start + timedelta(minutes=interval_idx * req.interval_minutes)
            int_end = int_start + timedelta(minutes=req.interval_minutes)

            for station_id, int_stn in mapped_stations:
                profile = self.BASE_DEMAND_MATRIX.get(int_stn, default_profile)
                base_arrivals, base_energy = profile[interval_idx % len(profile)]

                item = ForecastIntervalItem(
                    forecast_id=forecast_id,
                    scenario_id=req.scenario_id,
                    station_id=int_stn,
                    interval_start=int_start,
                    interval_end=int_end,
                    interval_minutes=req.interval_minutes,
                    predicted_arrivals=float(base_arrivals),
                    predicted_energy_kwh=float(base_energy),
                    model_version="mock-v1.0",
                    generated_at=gen_time,
                )
                intervals.append(item)

        stored_resp = ForecastResponse(
            forecast_id=forecast_id,
            scenario_id=req.scenario_id,
            model_version="mock-v1.0",
            generated_at=gen_time,
            intervals=intervals,
            interval_count=len(intervals),
            station_ids=[int_stn for _, int_stn in mapped_stations],
        )
        self._created_forecasts[forecast_id] = stored_resp
        self._last_successful_request = now.isoformat()

        return ForecastAcknowledgement(
            contract_version="1.0",
            forecast_id=forecast_id,
            scenario_id=req.scenario_id,
            status="generated",
            demand_type="baseline",
            generated_at=now,
            interval_minutes=req.interval_minutes,
            horizon_intervals=req.horizon_intervals,
            forecast_url=f"/api/v1/forecasts/{forecast_id}",
        )

    def get_forecast(self, forecast_id: str, scenario_id: Optional[str] = None) -> ForecastResponse:
        """Returns deterministic 6-interval forecast for the requested ID."""
        if forecast_id == "FC-NOTFOUND":
            raise EntityNotFoundError("Forecast", forecast_id)
        if forecast_id == "FC-INVALID":
            raise InvalidForecastError("Forecast format corrupted or missing mandatory fields")

        if forecast_id in self._created_forecasts:
            self._last_successful_request = datetime.now(timezone.utc).isoformat()
            return self._created_forecasts[forecast_id]

        # Stable pseudo-variation based on hash of forecast_id
        hash_factor = (sum(ord(c) for c in forecast_id) % 10) / 100.0  # +/- 0% to 9%

        intervals: List[ForecastIntervalItem] = []
        gen_time = self.base_start_time - timedelta(hours=2)
        active_stations = StationMapper.get_profile_stations()

        for interval_idx in range(6):
            int_start = self.base_start_time + timedelta(hours=interval_idx)
            int_end = int_start + timedelta(hours=1)

            for station_id in active_stations:
                profile = self.BASE_DEMAND_MATRIX.get(station_id, [(10.0, 200.0)] * 6)
                base_arrivals, base_energy = profile[interval_idx % len(profile)]
                arrivals = round(base_arrivals * (1.0 + hash_factor), 1)
                energy = round(base_energy * (1.0 + hash_factor), 1)

                item = ForecastIntervalItem(
                    forecast_id=forecast_id,
                    scenario_id=scenario_id,
                    station_id=station_id,
                    interval_start=int_start,
                    interval_end=int_end,
                    interval_minutes=60,
                    predicted_arrivals=arrivals,
                    predicted_energy_kwh=energy,
                    model_version="mock-v1.0",
                    generated_at=gen_time,
                )
                intervals.append(item)

        self._last_successful_request = datetime.now(timezone.utc).isoformat()

        return ForecastResponse(
            forecast_id=forecast_id,
            scenario_id=scenario_id,
            model_version="mock-v1.0",
            generated_at=gen_time,
            intervals=intervals,
            interval_count=len(intervals),
            station_ids=active_stations,
        )

    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates feedback receipt and returns acknowledgment."""
        feedback_id = payload.get("feedback_id", "FBD-DEFAULT")
        self._submitted_feedback[feedback_id] = payload
        self._last_successful_request = datetime.now(timezone.utc).isoformat()
        return {
            "status": "received",
            "feedback_id": feedback_id,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "message": "Feedback successfully processed by mock predictor adapter.",
        }

    def get_next_operational_adjustment(
        self,
        feedback_id: str,
        target_interval_start: str,
        target_interval_end: str,
        forecast_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Calculates authoritative adjusted operational demand by combining subsequent baseline
        with deferred unserved demand from the feedback record.
        """
        feedback = self._submitted_feedback.get(feedback_id)
        if not feedback:
            return None

        # Validate and derive interval index from target_interval_start
        try:
            if isinstance(target_interval_start, str):
                cleaned_str = target_interval_start.replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(cleaned_str)
            elif isinstance(target_interval_start, datetime):
                start_dt = target_interval_start
            else:
                raise ValueError("Unsupported timestamp type")
        except Exception as exc:
            raise InvalidForecastError(
                f"Invalid target_interval_start format '{target_interval_start}': {str(exc)}"
            )

        forecast_id = feedback.get("forecast_id")
        base_start = self.base_start_time
        if forecast_id and forecast_id in self._created_forecasts:
            created_fc = self._created_forecasts[forecast_id]
            if created_fc.intervals:
                base_start = created_fc.intervals[0].interval_start

        # Align timezone awareness
        if start_dt.tzinfo is None and base_start.tzinfo is not None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        elif start_dt.tzinfo is not None and base_start.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=None)

        diff_seconds = (start_dt - base_start).total_seconds()
        interval_idx = int(round(diff_seconds / 3600.0))

        # Explicit validation for out-of-horizon timestamps
        if diff_seconds < -60 or interval_idx < 0 or interval_idx >= 6:
            raise InvalidForecastError(
                f"Target interval start '{target_interval_start}' is outside the 6-interval forecast horizon "
                f"(derived interval index {interval_idx}, horizon start {base_start.isoformat()})."
            )

        station_outcomes = feedback.get("station_outcomes", [])
        deferred_fraction = feedback.get("deferred_fraction", 0.70)

        # Fallback profile for unknown station IDs (6 intervals of 10 arrivals / 200 kWh)
        default_station_profile = [(10.0, 200.0)] * 6

        adjustments = []
        # Next baseline factor
        for outcome in station_outcomes:
            stn_id = outcome.get("station_id")
            unserved = outcome.get("estimated_unserved", 0.0)
            deferred_veh = round(unserved * deferred_fraction, 1)

            # Average energy per unserved vehicle approximation
            pred_veh = outcome.get("predicted_arrivals", 1.0)
            pred_energy = outcome.get("predicted_energy_kwh", 20.0)
            avg_kwh_per_veh = (pred_energy / pred_veh) if pred_veh > 0 else 25.0
            deferred_kwh = round(deferred_veh * avg_kwh_per_veh, 1)

            # Look up baseline from created forecast if available, else matrix
            base_next_arrivals = None
            base_next_kwh = None
            if forecast_id and forecast_id in self._created_forecasts:
                for it in self._created_forecasts[forecast_id].intervals:
                    if it.station_id == stn_id and abs((it.interval_start - start_dt).total_seconds()) < 60:
                        base_next_arrivals = it.predicted_arrivals
                        base_next_kwh = it.predicted_energy_kwh
                        break

            if base_next_arrivals is None:
                station_profile = self.BASE_DEMAND_MATRIX.get(stn_id, default_station_profile)
                if 0 <= interval_idx < len(station_profile):
                    base_next_arrivals, base_next_kwh = station_profile[interval_idx]
                else:
                    base_next_arrivals, base_next_kwh = (10.0, 200.0)

            adjustments.append({
                "station_id": stn_id,
                "original_predicted_arrivals": base_next_arrivals,
                "original_predicted_energy_kwh": base_next_kwh,
                "deferred_vehicles_added": deferred_veh,
                "deferred_energy_kwh_added": deferred_kwh,
                "adjusted_predicted_arrivals": round(base_next_arrivals + deferred_veh, 1),
                "adjusted_predicted_energy_kwh": round(base_next_kwh + deferred_kwh, 1),
            })

        self._last_successful_request = datetime.now(timezone.utc).isoformat()

        return {
            "source_feedback_id": feedback_id,
            "parent_forecast_id": forecast_id,
            "target_interval_start": target_interval_start,
            "target_interval_end": target_interval_end,
            "station_adjustments": adjustments,
            "calculation_assumptions": {
                "deferred_fraction": deferred_fraction,
                "mode": "mock-deterministic-linear-deferral",
                "ownership": "optimizer-authoritative-adjustment",
            },
        }

    def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider_mode": "mock",
            "is_mock": True,
            "last_successful_request": self._last_successful_request,
            "active_mock_stations": len(self.MOCK_STATIONS),
        }
