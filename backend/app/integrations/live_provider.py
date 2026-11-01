import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from app.integrations.base import ForecastProviderAdapter
from app.schemas.forecast import (
    ForecastResponse,
    ForecastIntervalItem,
    ForecastCreateRequest,
    ForecastAcknowledgement,
    ForecastDetailRead,
    validate_forecast_horizon_integrity,
)
from app.schemas.external_feedback import (
    AllocationIntervalInput,
    StationAllocationFeedbackInput,
    PredictorFeedbackCreateRequest,
    PredictorFeedbackCreateResponse,
    AdjustedDemandResponse,
    AdjustedDemandIntervalRead,
    StationAdjustedDemandRead,
)
from app.integrations.station_mapper import StationMapper
from app.core.config import settings
from app.core.exceptions import (
    ProviderIntegrationError,
    EntityNotFoundError,
    InvalidForecastError,
    StationMappingError,
    IdempotencyConflictError,
)


class LiveForecastProvider(ForecastProviderAdapter):
    """
    HTTP client adapter communicating with the external EVCharge-Predict service over REST API.
    Enforces timeout, authentication, and safe error propagation.
    """
    _class_local_to_remote_feedback_ids: Dict[str, str] = {}

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_token: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.PREDICT_API_BASE_URL).rstrip("/")
        self.service_token = service_token or settings.PREDICT_SERVICE_TOKEN
        self.timeout = timeout or settings.PREDICT_TIMEOUT_SECONDS
        self._last_successful_request: Optional[str] = None
        self._local_to_remote_feedback_ids: Dict[str, str] = self._class_local_to_remote_feedback_ids

    @classmethod
    def register_feedback_mapping(cls, local_feedback_id: str, remote_feedback_id: str) -> None:
        """Registers a local-to-remote feedback ID mapping into class-level cache."""
        cls._class_local_to_remote_feedback_ids[local_feedback_id] = remote_feedback_id
        cls._class_local_to_remote_feedback_ids[remote_feedback_id] = remote_feedback_id

    def _get_headers(self, require_auth: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "EVCharge-Opt/1.0",
        }
        if require_auth:
            if not self.service_token or not str(self.service_token).strip():
                raise ProviderIntegrationError(
                    "Predictor service authorization token (PREDICT_SERVICE_TOKEN) is not configured for live provider.",
                    is_retryable=False,
                )
            headers["Authorization"] = f"Bearer {str(self.service_token).strip()}"
        return headers

    @staticmethod
    def _normalize_utc_datetime(dt_val: Union[datetime, str]) -> datetime:
        """
        Normalizes a string or datetime to a timezone-aware UTC datetime.
        Preserves exact instants across timezone equivalents and handles ISO strings.
        """
        if isinstance(dt_val, str):
            dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        elif isinstance(dt_val, datetime):
            dt = dt_val
        else:
            raise InvalidForecastError(f"Unsupported timestamp format: {dt_val}")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def create_forecast(self, req: ForecastCreateRequest) -> ForecastAcknowledgement:
        """
        Requests baseline forecast generation from EVCharge-Predict (POST /api/v1/forecasts).
        Enforces predictor 3-station support, validates acknowledgement (accepting 'completed' or 'generated'),
        and confirms forecast retrieval and 6-interval horizon integrity.
        """
        url = f"{self.base_url}/api/v1/forecasts"
        # Map internal station IDs to canonical predictor IDs, rejecting unsupported stations like ST-004 / ST-005
        mapped_stations = [
            StationMapper.to_external(s, validate_predictor_support=True)
            for s in req.station_ids
        ]

        payload = {
            "scenario_id": req.scenario_id,
            "station_ids": mapped_stations,
            "forecast_start": req.forecast_start.isoformat(),
            "interval_minutes": req.interval_minutes,
            "horizon_intervals": req.horizon_intervals,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=self._get_headers(), json=payload)
                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error during forecast creation: HTTP {response.status_code}",
                        is_retryable=True,
                    )
                if response.status_code not in (200, 201, 202):
                    raise ProviderIntegrationError(
                        f"Predictor rejected baseline forecast creation: HTTP {response.status_code}",
                        is_retryable=False,
                    )

                data = response.json()
                ack = ForecastAcknowledgement.model_validate(data)

                # Validate acknowledgement status: partner contract specifies 'completed', 'generated', or 'ready'
                if ack.status.lower() not in ("completed", "generated", "ready", "success"):
                    raise ProviderIntegrationError(
                        f"Predictor returned non-successful forecast status: '{ack.status}'",
                        is_retryable=False,
                    )

                # Immediately verify retrieval and horizon integrity
                forecast_data = self.get_forecast(ack.forecast_id, req.scenario_id)
                expected_internal_stations = [StationMapper.to_internal(s) for s in req.station_ids]
                validate_forecast_horizon_integrity(
                    forecast_data.intervals,
                    expected_horizon_intervals=req.horizon_intervals,
                    expected_interval_minutes=req.interval_minutes,
                    expected_station_ids=expected_internal_stations,
                )

                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return ack

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service connection failure during forecast creation: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def get_forecast(self, forecast_id: str, scenario_id: Optional[str] = None) -> ForecastResponse:
        url = f"{self.base_url}/api/v1/forecasts/{forecast_id}"
        params = {}
        if scenario_id:
            params["scenario_id"] = scenario_id

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers(), params=params)

                if response.status_code == 404:
                    raise EntityNotFoundError("Remote Forecast", forecast_id)

                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error: HTTP {response.status_code}",
                        is_retryable=True,
                    )
                if response.status_code != 200:
                    raise ProviderIntegrationError(
                        f"Failed to fetch forecast from predictor: HTTP {response.status_code}",
                        is_retryable=False,
                    )

                data = response.json()

                # Check if data adheres to the documented ForecastDetailRead contract (stations containing nested intervals)
                if "stations" in data:
                    try:
                        detail = ForecastDetailRead.model_validate(data)
                    except Exception as exc:
                        raise InvalidForecastError(
                            f"Predictor forecast response failed contract schema validation: {exc}"
                        ) from exc

                    model_version = "1.0"
                    if detail.model and detail.model.model_version:
                        model_version = detail.model.model_version

                    all_items: List[ForecastIntervalItem] = []
                    internal_station_ids: List[str] = []

                    for stn_entry in detail.stations:
                        try:
                            int_stn = StationMapper.to_internal(stn_entry.station_id)
                        except StationMappingError as exc:
                            raise InvalidForecastError(
                                f"Station '{stn_entry.station_id}' from predictor forecast cannot be mapped to any internal station: {exc.message}"
                            ) from exc

                        internal_station_ids.append(int_stn)

                        # Enforce exactly horizon.interval_count (6) intervals per station
                        if len(stn_entry.intervals) != detail.horizon.interval_count:
                            raise InvalidForecastError(
                                f"Station '{stn_entry.station_id}' returned {len(stn_entry.intervals)} intervals, "
                                f"expected exactly {detail.horizon.interval_count}."
                            )

                        for inv in stn_entry.intervals:
                            item = ForecastIntervalItem(
                                forecast_id=detail.forecast_id,
                                scenario_id=detail.scenario_id,
                                station_id=int_stn,
                                interval_start=inv.interval_start,
                                interval_end=inv.interval_end,
                                interval_minutes=detail.horizon.interval_minutes,
                                predicted_arrivals=float(inv.predicted_arrivals),
                                predicted_energy_kwh=float(inv.predicted_energy_kwh),
                                model_version=model_version,
                                generated_at=detail.generated_at,
                            )
                            all_items.append(item)

                    # Validate full horizon integrity across all intervals
                    validate_forecast_horizon_integrity(
                        all_items,
                        expected_horizon_intervals=detail.horizon.interval_count,
                        expected_interval_minutes=detail.horizon.interval_minutes,
                        expected_station_ids=internal_station_ids,
                    )

                    parsed = ForecastResponse(
                        forecast_id=detail.forecast_id,
                        scenario_id=detail.scenario_id,
                        model_version=model_version,
                        generated_at=detail.generated_at,
                        intervals=all_items,
                        interval_count=len(all_items),
                        station_ids=internal_station_ids,
                    )
                else:
                    # Backward compatibility for legacy flat intervals payload
                    try:
                        raw_parsed = ForecastResponse.model_validate(data)
                    except Exception as exc:
                        raise InvalidForecastError(
                            f"Predictor forecast response failed schema validation: {exc}"
                        ) from exc

                    mapped_intervals = []
                    for it in raw_parsed.intervals:
                        int_stn = StationMapper.to_internal(it.station_id)
                        if int_stn != it.station_id:
                            it = it.model_copy(update={"station_id": int_stn})
                        mapped_intervals.append(it)
                    mapped_stations = [StationMapper.to_internal(s) for s in raw_parsed.station_ids]

                    parsed = ForecastResponse(
                        forecast_id=raw_parsed.forecast_id,
                        scenario_id=raw_parsed.scenario_id,
                        model_version=raw_parsed.model_version,
                        generated_at=raw_parsed.generated_at,
                        intervals=mapped_intervals,
                        interval_count=len(mapped_intervals),
                        station_ids=mapped_stations,
                    )

                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return parsed

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service connection failure: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts local allocation feedback into the partner contract format (FeedbackCreateRequest)
        supporting partial or full interval sets (>= 1 interval) matching the originating forecast.
        Submits via POST /api/v1/feedback.
        Enforces:
        - HTTP 201: New feedback successfully accepted (FeedbackCreateResponse with is_duplicate=False)
        - HTTP 200: Identical retry accepted (FeedbackCreateResponse with is_duplicate=True)
        - HTTP 409: Conflicting payload with existing allocation_run_id (raises IdempotencyConflictError, never retried)
        - HTTP 401/403: Authentication errors (raises non-retryable ProviderIntegrationError)
        - HTTP 400/422: Validation error (raises InvalidForecastError)
        - Timeouts & HTTP 5xx: Connection / server errors (raises retryable ProviderIntegrationError)
        """
        allocation_run_id = payload.get("allocation_run_id") or payload.get("allocation_id")
        if not allocation_run_id:
            raise InvalidForecastError("allocation_run_id (or allocation_id) is required for feedback submission.")

        forecast_id = payload.get("forecast_id")
        if not forecast_id:
            raise InvalidForecastError("forecast_id is required for feedback submission.")

        scenario_id = payload.get("scenario_id") or "default_scenario"
        optimizer_version = payload.get("optimizer_version") or getattr(settings, "APP_VERSION", "opt-core-1.0")

        submitted_at_raw = payload.get("submitted_at")
        if isinstance(submitted_at_raw, datetime):
            submitted_at = submitted_at_raw if submitted_at_raw.tzinfo is not None else submitted_at_raw.replace(tzinfo=timezone.utc)
        elif isinstance(submitted_at_raw, str):
            submitted_at = datetime.fromisoformat(submitted_at_raw.replace("Z", "+00:00"))
        else:
            submitted_at = datetime.now(timezone.utc)

        local_feedback_id = payload.get("local_feedback_id") or payload.get("feedback_id") or allocation_run_id

        # Retrieve originating forecast to validate station identity and exact interval boundaries
        forecast_data = payload.get("originating_forecast") or payload.get("forecast_data")
        if not forecast_data:
            forecast_data = self.get_forecast(forecast_id, scenario_id=scenario_id)

        # Build lookup of valid forecast interval boundaries per canonical station
        forecast_intervals_by_station: Dict[str, List[tuple]] = {}
        if isinstance(forecast_data, dict):
            if "stations" in forecast_data:
                for stn in forecast_data["stations"]:
                    canonical_stn = StationMapper.to_external(stn["station_id"], validate_predictor_support=True)
                    for it in stn.get("intervals", []):
                        s = it["interval_start"] if isinstance(it, dict) else it.interval_start
                        e = it["interval_end"] if isinstance(it, dict) else it.interval_end
                        s_dt = self._normalize_utc_datetime(s)
                        e_dt = self._normalize_utc_datetime(e)
                        forecast_intervals_by_station.setdefault(canonical_stn, []).append((s_dt, e_dt))
            elif "intervals" in forecast_data:
                for it in forecast_data["intervals"]:
                    canonical_stn = StationMapper.to_external(it["station_id"] if isinstance(it, dict) else it.station_id, validate_predictor_support=True)
                    s = it["interval_start"] if isinstance(it, dict) else it.interval_start
                    e = it["interval_end"] if isinstance(it, dict) else it.interval_end
                    s_dt = self._normalize_utc_datetime(s)
                    e_dt = self._normalize_utc_datetime(e)
                    forecast_intervals_by_station.setdefault(canonical_stn, []).append((s_dt, e_dt))
        elif hasattr(forecast_data, "stations"):
            for stn in forecast_data.stations:
                canonical_stn = StationMapper.to_external(stn.station_id, validate_predictor_support=True)
                for it in stn.intervals:
                    s_dt = self._normalize_utc_datetime(it.interval_start)
                    e_dt = self._normalize_utc_datetime(it.interval_end)
                    forecast_intervals_by_station.setdefault(canonical_stn, []).append((s_dt, e_dt))
        elif hasattr(forecast_data, "intervals"):
            for it in forecast_data.intervals:
                canonical_stn = StationMapper.to_external(it.station_id, validate_predictor_support=True)
                s_dt = self._normalize_utc_datetime(it.interval_start)
                e_dt = self._normalize_utc_datetime(it.interval_end)
                forecast_intervals_by_station.setdefault(canonical_stn, []).append((s_dt, e_dt))

        # Build StationAllocationFeedbackInput list
        stations_input: List[StationAllocationFeedbackInput] = []

        if "stations" in payload:
            # Caller provided explicit station intervals (partial or full interval sets)
            for stn_raw in payload["stations"]:
                raw_stn_id = stn_raw.get("station_id")
                canonical_stn_id = StationMapper.to_external(raw_stn_id, validate_predictor_support=True)

                if canonical_stn_id not in forecast_intervals_by_station:
                    raise InvalidForecastError(
                        f"Station '{raw_stn_id}' (canonical: '{canonical_stn_id}') is not part of originating forecast '{forecast_id}'."
                    )
                valid_boundaries = forecast_intervals_by_station[canonical_stn_id]

                raw_invs = stn_raw.get("intervals", [])
                if not raw_invs:
                    raise InvalidForecastError(
                        f"Station '{raw_stn_id}' must contain at least one feedback interval."
                    )

                parsed_invs: List[AllocationIntervalInput] = []
                for inv_data in raw_invs:
                    if isinstance(inv_data, AllocationIntervalInput):
                        s = self._normalize_utc_datetime(inv_data.interval_start)
                        e = self._normalize_utc_datetime(inv_data.interval_end)
                        alloc_kwh = inv_data.allocated_energy_kwh
                        cap_kw = inv_data.available_capacity_kw
                        unmet_kwh = inv_data.reported_unmet_demand_kwh
                    else:
                        s_raw = inv_data.get("interval_start")
                        e_raw = inv_data.get("interval_end")
                        s = self._normalize_utc_datetime(s_raw)
                        e = self._normalize_utc_datetime(e_raw)
                        alloc_kwh = inv_data.get("allocated_energy_kwh")
                        cap_kw = inv_data.get("available_capacity_kw")
                        unmet_kwh = inv_data.get("reported_unmet_demand_kwh")

                    if s >= e:
                        raise InvalidForecastError(f"interval_start ({s}) must be before interval_end ({e}).")

                    # Verify submitted interval matches an interval in the originating forecast exactly
                    matched_boundary = None
                    for (f_s, f_e) in valid_boundaries:
                        if s == f_s and e == f_e:
                            matched_boundary = (f_s, f_e)
                            break

                    if not matched_boundary:
                        raise InvalidForecastError(
                            f"Submitted interval [{s.isoformat()} - {e.isoformat()}) for station '{canonical_stn_id}' "
                            f"does not match any interval in originating forecast '{forecast_id}'."
                        )

                    parsed_invs.append(
                        AllocationIntervalInput(
                            interval_start=matched_boundary[0],
                            interval_end=matched_boundary[1],
                            allocated_energy_kwh=float(alloc_kwh) if alloc_kwh is not None else None,
                            available_capacity_kw=float(cap_kw) if cap_kw is not None else None,
                            reported_unmet_demand_kwh=float(unmet_kwh) if unmet_kwh is not None else None,
                        )
                    )

                stations_input.append(
                    StationAllocationFeedbackInput(
                        station_id=canonical_stn_id,
                        intervals=parsed_invs,
                    )
                )
        elif "station_outcomes" in payload:
            # Construct partial feedback intervals for the allocated interval; do not insert null intervals
            station_outcomes = payload["station_outcomes"]
            alloc_start_raw = payload.get("interval_start")
            alloc_end_raw = payload.get("interval_end")
            if not alloc_start_raw or not alloc_end_raw:
                raise InvalidForecastError("interval_start and interval_end are required with station_outcomes.")

            alloc_start = self._normalize_utc_datetime(alloc_start_raw)
            alloc_end = self._normalize_utc_datetime(alloc_end_raw)
            if alloc_start >= alloc_end:
                raise InvalidForecastError(f"interval_start ({alloc_start}) must be before interval_end ({alloc_end}).")

            for outcome in station_outcomes:
                raw_stn = outcome.get("station_id")
                canonical_stn = StationMapper.to_external(raw_stn, validate_predictor_support=True)
                if canonical_stn not in forecast_intervals_by_station:
                    raise InvalidForecastError(
                        f"Station '{raw_stn}' (canonical: '{canonical_stn}') is not part of originating forecast '{forecast_id}'."
                    )

                valid_boundaries = forecast_intervals_by_station[canonical_stn]
                matched_boundary = None
                for (f_s, f_e) in valid_boundaries:
                    if alloc_start == f_s and alloc_end == f_e:
                        matched_boundary = (f_s, f_e)
                        break

                if not matched_boundary:
                    raise InvalidForecastError(
                        f"Feedback interval [{alloc_start.isoformat()} - {alloc_end.isoformat()}) for station '{canonical_stn}' "
                        f"does not match any interval in originating forecast '{forecast_id}'."
                    )

                # Distinguish energy (kWh) and power (kW) from vehicle arrivals (counts)
                # Preserve valid 0.0 numeric values using explicit is not None checks
                if outcome.get("allocated_energy_kwh") is not None:
                    alloc_energy = outcome["allocated_energy_kwh"]
                elif outcome.get("estimated_served_energy_kwh") is not None:
                    alloc_energy = outcome["estimated_served_energy_kwh"]
                elif outcome.get("allocated_power_kw") is not None:
                    alloc_energy = outcome["allocated_power_kw"]
                else:
                    alloc_energy = 0.0

                if outcome.get("available_capacity_kw") is not None:
                    avail_cap = outcome["available_capacity_kw"]
                elif outcome.get("allocated_power_kw") is not None:
                    avail_cap = outcome["allocated_power_kw"]
                else:
                    avail_cap = None

                if outcome.get("reported_unmet_demand_kwh") is not None:
                    unmet_energy = outcome["reported_unmet_demand_kwh"]
                elif outcome.get("estimated_unserved_energy_kwh") is not None:
                    unmet_energy = outcome["estimated_unserved_energy_kwh"]
                elif outcome.get("deferred_energy_kwh") is not None:
                    unmet_energy = outcome["deferred_energy_kwh"]
                else:
                    unmet_energy = 0.0

                single_inv = AllocationIntervalInput(
                    interval_start=matched_boundary[0],
                    interval_end=matched_boundary[1],
                    allocated_energy_kwh=float(alloc_energy) if alloc_energy is not None else None,
                    available_capacity_kw=float(avail_cap) if avail_cap is not None else None,
                    reported_unmet_demand_kwh=float(unmet_energy) if unmet_energy is not None else None,
                )

                stations_input.append(
                    StationAllocationFeedbackInput(
                        station_id=canonical_stn,
                        intervals=[single_inv],
                    )
                )
        else:
            raise InvalidForecastError(
                "Feedback payload must provide either 'stations' or 'station_outcomes'."
            )

        if not stations_input:
            raise InvalidForecastError("No valid station allocation intervals could be constructed for feedback.")

        feedback_req = PredictorFeedbackCreateRequest(
            contract_version="1.0",
            allocation_run_id=allocation_run_id,
            forecast_id=forecast_id,
            scenario_id=scenario_id,
            submitted_at=submitted_at,
            optimizer_version=str(optimizer_version),
            stations=stations_input,
        )

        url = f"{self.base_url}/api/v1/feedback"
        payload_data = feedback_req.model_dump(mode="json")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=self._get_headers(), json=payload_data)

                if response.status_code in (401, 403):
                    raise ProviderIntegrationError(
                        f"Predictor authentication failure (HTTP {response.status_code}): {response.text}",
                        is_retryable=False,
                    )

                if response.status_code == 409:
                    err_msg = "Conflict: allocation_run_id was already submitted with differing payload."
                    try:
                        err_json = response.json()
                        if "detail" in err_json:
                            err_msg = err_json["detail"]
                    except Exception:
                        pass
                    raise IdempotencyConflictError(
                        f"Predictor rejected feedback submission due to allocation_run_id conflict (HTTP 409): {err_msg}",
                        idempotency_key=allocation_run_id,
                    )

                if response.status_code in (400, 422):
                    raise InvalidForecastError(
                        f"Predictor rejected feedback submission: HTTP {response.status_code} - {response.text}"
                    )

                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error: HTTP {response.status_code}",
                        is_retryable=True,
                    )

                if response.status_code not in (200, 201):
                    raise ProviderIntegrationError(
                        f"Unexpected predictor feedback response: HTTP {response.status_code} - {response.text}",
                        is_retryable=False,
                    )

                ack = PredictorFeedbackCreateResponse.model_validate(response.json())

                # Track local-to-remote feedback mapping
                if local_feedback_id:
                    self._local_to_remote_feedback_ids[local_feedback_id] = ack.feedback_id
                self._local_to_remote_feedback_ids[allocation_run_id] = ack.feedback_id
                self._local_to_remote_feedback_ids[ack.feedback_id] = ack.feedback_id

                self._last_successful_request = datetime.now(timezone.utc).isoformat()

                return {
                    "status": ack.status,
                    "feedback_id": ack.feedback_id,  # Predictor-generated feedback_id (e.g. fbk_...)
                    "remote_feedback_id": ack.feedback_id,
                    "local_feedback_id": local_feedback_id,
                    "allocation_run_id": ack.allocation_run_id,
                    "forecast_id": ack.forecast_id,
                    "scenario_id": ack.scenario_id,
                    "is_duplicate": ack.is_duplicate,
                    "received_at": ack.received_at.isoformat() if hasattr(ack.received_at, "isoformat") else str(ack.received_at),
                    "feedback_url": ack.feedback_url,
                }

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service connection failure during feedback submission: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def get_next_operational_adjustment(
        self,
        feedback_id: str,
        target_interval_start: str,
        target_interval_end: str,
        forecast_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves adjusted operational demand from the documented predictor endpoint:
        GET /api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id={feedback_id}

        Maps nested station/interval results into EVCharge-Opt's internal representation
        (StationOperationalAdjustmentItem format) without confusing energy values (kWh) with vehicle counts.
        """
        if not forecast_id:
            raise ProviderIntegrationError(
                "forecast_id is required to fetch adjusted demand from predictor.",
                is_retryable=False,
            )

        # Resolve predictor remote feedback ID if a local ID was passed
        remote_feedback_id = self._local_to_remote_feedback_ids.get(feedback_id, feedback_id)

        url = f"{self.base_url}/api/v1/forecasts/{forecast_id}/adjusted-demand"
        params = {"feedback_id": remote_feedback_id}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self._get_headers(), params=params)

                if response.status_code == 404:
                    return None

                if response.status_code in (401, 403):
                    raise ProviderIntegrationError(
                        f"Predictor authentication failure (HTTP {response.status_code}): {response.text}",
                        is_retryable=False,
                    )

                if response.status_code >= 500:
                    raise ProviderIntegrationError(
                        f"Predictor service error: HTTP {response.status_code}",
                        is_retryable=True,
                    )

                if response.status_code != 200:
                    raise ProviderIntegrationError(
                        f"Predictor error retrieving adjusted demand: HTTP {response.status_code} - {response.text}",
                        is_retryable=False,
                    )

                data = response.json()

                # Backward compatibility for legacy test payloads without "stations"
                if "stations" not in data:
                    self._last_successful_request = datetime.now(timezone.utc).isoformat()
                    return data

                try:
                    adj_model = AdjustedDemandResponse.model_validate(data)
                except Exception as exc:
                    raise InvalidForecastError(
                        f"Predictor returned invalid AdjustedDemandResponse schema: {exc}"
                    ) from exc

                target_start_dt = self._normalize_utc_datetime(target_interval_start)
                target_end_dt = self._normalize_utc_datetime(target_interval_end)
                if target_start_dt >= target_end_dt:
                    raise InvalidForecastError(
                        f"target_interval_start ({target_start_dt}) must be before target_interval_end ({target_end_dt})."
                    )

                adjustments = []
                for stn_entry in adj_model.stations:
                    try:
                        int_stn = StationMapper.to_internal(stn_entry.station_id)
                    except StationMappingError as exc:
                        raise InvalidForecastError(
                            f"Adjusted demand station '{stn_entry.station_id}' cannot be mapped to any internal station: {exc.message}"
                        ) from exc

                    matching_inv = None
                    for inv in stn_entry.intervals:
                        inv_start = self._normalize_utc_datetime(inv.interval_start)
                        inv_end = self._normalize_utc_datetime(inv.interval_end)
                        if inv_start == target_start_dt and inv_end == target_end_dt:
                            matching_inv = inv
                            break

                    if not matching_inv:
                        raise InvalidForecastError(
                            f"Target interval [{target_start_dt.isoformat()} - {target_end_dt.isoformat()}) "
                            f"was not found in predictor adjusted demand intervals for station '{stn_entry.station_id}'."
                        )

                    # Maintain strict separation between vehicle counts (arrivals) and energy (kWh)
                    orig_arrivals = float(matching_inv.baseline_arrivals)
                    orig_kwh = float(matching_inv.baseline_energy_kwh)
                    adj_kwh = float(matching_inv.adjusted_operational_demand_kwh)
                    # Baseline arrivals strictly preserved without modification
                    adj_arrivals = orig_arrivals
                    deferred_kwh = max(0.0, round(adj_kwh - orig_kwh, 4))

                    adjustments.append({
                        "station_id": int_stn,
                        "original_predicted_arrivals": orig_arrivals,
                        "original_predicted_energy_kwh": orig_kwh,
                        "deferred_vehicles_added": 0.0,
                        "deferred_energy_kwh_added": deferred_kwh,
                        "adjusted_predicted_arrivals": adj_arrivals,
                        "adjusted_predicted_energy_kwh": adj_kwh,
                    })

                self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return {
                    "source_feedback_id": feedback_id,
                    "parent_forecast_id": forecast_id,
                    "target_interval_start": target_interval_start,
                    "target_interval_end": target_interval_end,
                    "station_adjustments": adjustments,
                    "calculation_assumptions": {
                        "demand_type": adj_model.demand_type,
                        "adjustment_policy_version": adj_model.adjustment_policy_version,
                        "policy_description": adj_model.policy_description,
                        "policy_limitations": adj_model.policy_limitations,
                        "computed_at": adj_model.computed_at.isoformat() if hasattr(adj_model.computed_at, "isoformat") else str(adj_model.computed_at),
                    },
                    "raw_adjusted_demand": data,
                }

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderIntegrationError(
                f"Predictor service network error retrieving adjusted demand: {exc.__class__.__name__}",
                is_retryable=True,
            ) from exc

    def check_health(self) -> Dict[str, Any]:
        url = f"{self.base_url}/healthz"
        try:
            with httpx.Client(timeout=min(self.timeout, 5.0)) as client:
                response = client.get(url, headers=self._get_headers(require_auth=False))
                is_healthy = response.status_code == 200
                if is_healthy:
                    self._last_successful_request = datetime.now(timezone.utc).isoformat()
                return {
                    "status": "healthy" if is_healthy else "degraded",
                    "provider_mode": "live",
                    "is_mock": False,
                    "status_code": response.status_code,
                    "last_successful_request": self._last_successful_request,
                }
        except Exception as exc:
            return {
                "status": "unreachable",
                "provider_mode": "live",
                "is_mock": False,
                "error": exc.__class__.__name__,
                "last_successful_request": self._last_successful_request,
            }
