# EVCharge-Opt ↔ EVCharge-Predict Deep Integration Audit & Release-Readiness Review

**Document Version:** 1.0
**Audit Date:** October 28, 2026
**Auditor:** Senior Backend Engineer, API Integration Architect & Software Test Auditor
**Project Workspace:** `/Users/bharanikumar.j/Documents/EVChargeOptimization`
**Git Branch:** `feature/predict-contract-alignment`
**Head Commit:** `0998fcb` (`fix: shorten Alembic revision identifier for PostgreSQL compatibility`)
**Target Partner Service:** EVCharge-Predict (`https://evcharge-predict.onrender.com`)
**Optimizer Hosted Service:** EVCharge-Opt API (`https://evcharge-opt-api.onrender.com`), Web Frontend (`https://evcharge-opt.onrender.com`)

---

## 1. Executive Summary & Integration-Readiness Verdict

### Overall Verdict: **READY WITH CONDITIONS**

EVCharge-Opt has achieved robust protocol alignment with the EVCharge-Predict Phase 1 and Phase 2 integration contracts. The core forecasting client, nested station-interval parser, partial-interval feedback payload builder, numeric fallback preservation (retaining valid `0.0` values), unit separation (strictly separating vehicle arrival counts from kWh energy), and exact UTC interval-boundary matching are properly implemented. All **106 backend tests pass** and the frontend production build passes cleanly.

However, **live joint testing against the hosted partner endpoint cannot safely proceed** until five blocking conditions (P0) are remediated:

1. **Circular Import Crash (Code-level):** `backend/app/schemas/external_feedback.py` imports `StationMapper` at module top-level, causing `import app.services` to fail immediately with an `ImportError` due to a circular dependency loop through `app.integrations.live_provider`.
2. **Missing Fail-Fast Token Enforcement (Security):** `LiveForecastProvider` silently omits the `Authorization` header when `PREDICT_SERVICE_TOKEN` is unset or empty, rather than aborting or failing fast before sending unauthenticated HTTP requests to protected partner endpoints.
3. **HTTP 409 Conflict Masking (Business Logic):** When EVCharge-Predict rejects a conflicting feedback retry with HTTP 409, `FeedbackService` catches the resulting `IdempotencyConflictError` inside a generic `except Exception` handler, incorrectly recording a `failed` record and returning `HTTP 201 Created` to the client instead of propagating HTTP 409.
4. **Partner Secret Token Provisioning (Environment):** The shared service secret (`PREDICT_SERVICE_TOKEN`) has not been provisioned in the Render dashboard for `evcharge-opt-api`.
5. **Physical Station Correspondence Safeguard (Operational):** Proposed mappings (`STN-01..03` ↔ `ST-001..003`) remain legally and physically `UNCONFIRMED_PROPOSAL`. Live allocation requires the operational flag `CONFIRM_PHYSICAL_STATION_MAPPINGS=true` and `STATION_INTEGRATION_PROFILE=three_station_integration`.

---

## 2. Scope, Git Branch, Working-Tree State & Verification Performed

### 2.1. Git Working-Tree Audit

```
Repository Root: /Users/bharanikumar.j/Documents/EVChargeOptimization
Current Branch: feature/predict-contract-alignment
Head Commit: 0998fcb fix: shorten Alembic revision identifier for PostgreSQL compatibility
```

**Tracked Modified Files (8):**
- `backend/app/integrations/live_provider.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/external_feedback.py`
- `backend/app/schemas/forecast.py`
- `backend/app/services/allocation_service.py`
- `backend/app/services/feedback_service.py`
- `backend/tests/integration/test_live_provider_client.py`
- `backend/tests/unit/test_forecast_validation.py`

**Untracked Files (1):**
- `backend/tests/integration/test_simulated_e2e_workflow.py`

**Working Tree Cleanliness:**
- `git diff --check`: Passed with exit code 0 (zero trailing whitespace, carriage returns, or merge conflict markers).
- No uncommitted `.env`, `.db`, or `.sqlite` files are tracked. `.gitignore` comprehensively excludes credentials, databases, cache directories, and build artifacts.

### 2.2. Independent Verification Executed
- Full backend pytest run: `cd backend && ../.venv/bin/python -m pytest` → **106 passed, 1 deprecation warning in 1.36s**.
- Frontend production build: `npm --prefix frontend run build` → **Passed in 2.40s** (`tsc && vite build` built `dist/` cleanly).
- Alembic migration check: `cd backend && ../.venv/bin/alembic check` → Identified schema differences between model definitions and Alembic revision 002.
- Direct module import isolation test: `PYTHONPATH=backend .venv/bin/python -c "import app.services"` → Reproducible `ImportError` isolated.

---

## 3. Architecture & Data-Flow Summary (Code-Grounded)

The interaction between EVCharge-Opt and EVCharge-Predict is depicted below:

```
[EVCharge-Opt UI] (Browser)
       │
       ▼ (HTTPS REST, Bearer Token NOT exposed)
[evcharge-opt-api] (FastAPI Backend)
       │
       ├─► AllocationEngine (Deterministic scheduling & impact simulation)
       │
       ├─► ForecastProviderAdapter
       │         │
       │         ├─► MockForecastProvider (Default: deterministic offline fixtures)
       │         │
       │         └─► LiveForecastProvider (Backend-to-Backend HTTPX Client)
       │                   │ (Authorization: Bearer <PREDICT_SERVICE_TOKEN>)
       │                   ▼
       │     [EVCharge-Predict API] (https://evcharge-predict.onrender.com)
       │                   │
       │                   ├─► POST /api/v1/forecasts
       │                   ├─► GET  /api/v1/forecasts/{id}
       │                   ├─► POST /api/v1/feedback
       │                   └─► GET  /api/v1/forecasts/{id}/adjusted-demand?feedback_id=...
       │
       └─► PostgreSQL / SQLite Database
             ├─► scenarios
             ├─► allocation_runs & allocation_results
             ├─► feedback_records (local feedback_id: FBD-...)
             ├─► operational_adjustments (contains remote_feedback_id: fbk_...)
             └─► audit_events (immutable event log)
```

### Data Flow Steps
1. **Forecast Ingestion:** `LiveForecastProvider.get_forecast()` fetches from `GET /api/v1/forecasts/{forecast_id}`, parses `ForecastDetailRead`, translates canonical external IDs (`ST-001..003`) to internal IDs (`STN-01..03`), and validates the 6-interval hourly horizon.
2. **Optimization Execution:** `AllocationService.run_allocation()` takes requested interval boundaries, maps station power/charger limits and shared grid constraints, runs `AllocationEngine.optimize()`, and stores the simulation outcome.
3. **Feedback Submission:** `FeedbackService.submit_allocation_feedback()` compiles allocation outcomes into `PredictorFeedbackCreateRequest`, and `LiveForecastProvider.submit_feedback()` posts to `POST /api/v1/feedback`. The predictor returns `PredictorFeedbackCreateResponse` with predictor feedback ID (`fbk_...`).
4. **Operational Adjustment Retrieval:** `LiveForecastProvider.get_next_operational_adjustment()` queries `GET /api/v1/forecasts/{id}/adjusted-demand?feedback_id={fbk_...}` and derives the operational demand envelope (`max(baseline, allocated)`).
5. **Adjustment Persistence:** `OperationalAdjustment` is stored in the database with `source_feedback_id = local_feedback_id` and `calculation_assumptions_json` containing `remote_feedback_id`.
6. **Subsequent Interval Optimization:** `AllocationService.run_allocation()` executes the subsequent interval using `operational_adjustment_id`, validating that target interval boundaries and parent forecast IDs match exactly.

---

## 4. Audit A — Partner API Contract Compatibility Matrix

Analysis based on `EVCharge-Opt-Integration-Guide.md` and `openapi_schema.json`:

| Documented Endpoint | HTTP Method | Expected Status Codes | EVCharge-Opt Implementation (`live_provider.py`) | Contract Compliance & Divergence Notes |
| :--- | :--- | :--- | :--- | :--- |
| `/api/v1/forecasts` | `POST` | 201, 400, 404, 422, 503 | `create_forecast()` (lines 78–141) | **COMPLIANT with Minor Gap:** Handles 201/200; raises `ProviderIntegrationError(is_retryable=True)` on $\ge 500$; maps internal station IDs to canonical external IDs. *Gap:* Discards error body text on 400 (`InsufficientHistoryError`) and 422. |
| `/api/v1/forecasts/{id}` | `GET` | 200, 404, 422, 500 | `get_forecast()` (lines 142–268) | **COMPLIANT with Minor Gap:** Validates `ForecastDetailRead`; handles nested stations/intervals; validates 6 hourly intervals. *Gap:* Discards response error body on non-200. |
| `/api/v1/feedback` | `POST` | 201, 200, 400, 404, 409, 422, 500 | `submit_feedback()` (lines 269–576) | **COMPLIANT:** Handles HTTP 201 (initial), HTTP 200 (`is_duplicate: true`), HTTP 409 (conflict -> `IdempotencyConflictError`), and HTTP 401/403 (non-retryable auth error). *Note on OpenAPI:* OpenAPI schema defines `201: No content`, whereas Integration Guide documents `FeedbackCreateResponse`; EVCharge-Opt correctly parses `FeedbackCreateResponse` on both 201 and 200. |
| `/api/v1/feedback/{id}` | `GET` | 200, 404, 422 | *Not Implemented in Live Provider* | **INFORMATIONAL GAP:** Documented in guide section 5.4 (`FeedbackDetailRead`), but not currently called or required by optimizer workflows. |
| `/api/v1/forecasts/{id}/adjusted-demand` | `GET` | 200, 404, 422, 500 | `get_next_operational_adjustment()` (lines 577–712) | **COMPLIANT:** Correctly uses query parameter `feedback_id`; parses `AdjustedDemandResponse`; strictly separates energy (kWh) from vehicle arrivals (counts); validates both start and end interval boundaries. |
| `/api/v1/sessions` | `GET` | 200, 422 | *Not Implemented in Live Provider* | **INFORMATIONAL GAP:** Documented in guide section 5.7 for pre-flight data sufficiency check (< 5 sessions in 21 days); not currently called by EVCharge-Opt. |
| `/api/v1/stations` | `GET` | 200, 422 | *Not Implemented in Live Provider* | **INFORMATIONAL GAP:** Documented in guide section 5.6; station mappings are managed via local `StationMapper` registry. |

---

## 5. Audit B — Feedback ID Correctness, Lifecycle & Persistence

### 5.1. Feedback ID Duality
- **Local Feedback ID:** Formatted as `FBD-XXXXXXXX` (e.g., `FBD-1A2B3C4D`), generated by `FeedbackService` before submission and stored as primary key in `feedback_records.feedback_id`.
- **Remote Predictor Feedback ID:** Formatted as `fbk_...` (e.g., `fbk_7a8b9c0d1e2f`), generated by EVCharge-Predict upon accepting `POST /api/v1/feedback`.

### 5.2. ID Flow & Persistence Trace
1. **Submission:** `FeedbackService.submit_allocation_feedback()` generates `feedback_id = f"FBD-{uuid.uuid4().hex[:8].upper()}"`. It passes `payload` to `provider.submit_feedback(payload)`.
2. **Provider Parsing:** `LiveForecastProvider.submit_feedback()` extracts `ack.feedback_id` (`fbk_...`) and registers:
   ```python
   self._local_to_remote_feedback_ids[local_feedback_id] = ack.feedback_id
   self._local_to_remote_feedback_ids[allocation_run_id] = ack.feedback_id
   ```
   It returns `{"status": ack.status, "feedback_id": ack.feedback_id, "remote_feedback_id": ack.feedback_id, ...}`.
3. **Adjustment Fetching:** `FeedbackService` captures `remote_feedback_id` and passes `target_feedback_id = remote_feedback_id or feedback_id` into `provider.get_next_operational_adjustment(feedback_id=target_feedback_id, ...)`.
4. **Database Storage:**
   - In `feedback_records`: Stores local `feedback_id`.
   - In `operational_adjustments`: Stores `source_feedback_id = feedback_id` (local foreign key), and stores `remote_feedback_id` inside `calculation_assumptions_json`.
   - In `audit_events`: Stores `remote_feedback_id` in `details_json`.

### 5.3. Volatility and Multi-Instance / Restart Analysis
- **Vulnerability Identified:** The class-level dictionary `_class_local_to_remote_feedback_ids` in `LiveForecastProvider` is **ephemeral**. If the backend restarts (or across multi-worker processes on Render) before an operational adjustment is retrieved, the in-memory dictionary is lost.
- **Durable Solution Without Migration:** When resolving feedback IDs in `LiveForecastProvider`, add a fallback query to check `OperationalAdjustment.calculation_assumptions_json` or `AuditEvent.details_json` if `feedback_id` is missing from the in-memory map.
- **Target Solution (Future Phase):** Add a nullable column `remote_feedback_id = mapped_column(String(64), nullable=True)` to `FeedbackRecord` via an Alembic migration.

---

## 6. Audit C — Authentication and Secrets

### 6.1. Bearer Token Enforcement
- **Partner Requirement:** EVCharge-Predict enforces `Authorization: Bearer <API_AUTH_TOKEN>` on all `/api/v1/forecasts*`, `/api/v1/feedback*`, `/api/v1/stations*`, and `/api/v1/sessions*` endpoints, returning HTTP 401 on missing tokens and HTTP 403 on invalid tokens.
- **Optimizer Implementation (`live_provider.py:52-60`):**
  ```python
  def _get_headers(self) -> Dict[str, str]:
      headers = {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "User-Agent": "EVCharge-Opt/1.0",
      }
      if self.service_token:
          headers["Authorization"] = f"Bearer {self.service_token}"
      return headers
  ```
- **Vulnerability:** If `PREDICT_PROVIDER_MODE=live` but `PREDICT_SERVICE_TOKEN` is unset or empty, `_get_headers()` silently omits the header. It should immediately raise a `ProviderIntegrationError` before attempting network I/O.

### 6.2. Secrets Leakage Audit
- **Frontend Inspection:** `frontend/` source code inspected. Only `VITE_API_BASE_URL` is used. No provider tokens or partner URLs are exposed to client JavaScript.
- **API Responses & Diagnostics:** Inspected `backend/app/api/v1/health.py` and `backend/tests/api/test_health.py`. `/integration/health` exposes `status`, `provider_mode`, and sanitized `configured_api_base_url` (with credentials stripped via `get_safe_predict_url()`). Zero credentials exposed in health or API outputs.
- **Log Sanitation:** Inspected `backend/app/core/logging.py`. Secret tokens are never logged.

---

## 7. Audit D — Forecast Validation and Station Mapping

### 7.1. Canonical Station ID Mapping
- EVCharge-Opt internal stations (`STN-01`, `STN-02`, `STN-03`) map strictly to EVCharge-Predict canonical stations (`ST-001`, `ST-002`, `ST-003`).
- Internal stations `STN-04` and `STN-05` are categorized as `UNSUPPORTED_BY_MODEL` and fail fast with `StationMappingError` if sent to live provider endpoints.
- Ambiguous re-registration or conflicting mapping attempts are rejected by `StationMapper.register_mapping()`.

### 7.2. Physical Station Correspondence Safeguard
- `StationMapper` explicitly classifies candidate mappings as `UNCONFIRMED_PROPOSAL`.
- When `is_live_mode` is active, `AllocationService` enforces:
  ```python
  require_physical_confirmed = is_live_mode and not getattr(settings, "CONFIRM_PHYSICAL_STATION_MAPPINGS", False)
  ```
- If physical confirmation is missing in live mode, any allocation attempt raises `StationMappingError`, preventing unverified real-world charger scheduling.

### 7.3. Exact UTC Interval Boundary Validation
- `AllocationService.run_allocation()` normalizes interval timestamps to UTC and matches both `interval_start` and `interval_end` against forecast intervals.
- Any boundary deviation (including 30-second misalignments) is rejected with `InvalidForecastError`. Timezone-equivalent offsets (e.g. `+05:30` vs UTC `Z`) are correctly normalized and matched.
- Inverted interval timestamps (`interval_start >= interval_end`) are rejected.

---

## 8. Audit E — Adjusted Demand and Optimization Correctness

### 8.1. Semantic Unit Separation
- Vehicle arrivals (`predicted_arrivals`, integer counts) and energy (`predicted_energy_kwh`, kWh) are kept strictly separate.
- In `LiveForecastProvider.get_next_operational_adjustment()`, `baseline_arrivals` are preserved without modification, and `adjusted_operational_demand_kwh` is assigned strictly to energy fields.
- `validate_energy_power_vehicle_semantics()` in `app/optimization/heuristics.py` asserts dimensional separation between vehicle sessions, kW power, and kWh energy.

### 8.2. Operational Planning Heuristic
- The partner formula:
  $$\text{adjusted\_operational\_demand\_kwh} = \max(\text{baseline\_predicted\_energy\_kwh}, \text{allocated\_energy\_kwh})$$
  is documented in `backend/app/optimization/heuristics.py` as an operational scheduling envelope reflecting grid curtailment decisions, not verified physical driver demand.

### 8.3. Zero-Value Preservation
- Numeric fallback logic in `live_provider.py` lines 448–472 uses explicit `is not None` checks:
  ```python
  if outcome.get("allocated_energy_kwh") is not None:
      alloc_energy = outcome["allocated_energy_kwh"]
  ```
  This preserves legitimate `0.0` values and prevents truthiness fallback corruption.

### 8.4. Operational Adjustment Error Suppression Finding
- In `FeedbackService.submit_allocation_feedback()` lines 170 and 282:
  ```python
  try:
      adj_response = provider.get_next_operational_adjustment(...)
  except Exception:
      adj_response = None
  ```
  This bare exception handler suppresses all adjustment lookup errors without logging, leaving no trace in `FeedbackRecord` or console logs.

---

## 9. Audit F — Simulation Mode vs Live Provider Separation

EVCharge-Opt strictly separates provider selection from optimization/simulation execution:
1. **Forecast Provider Adapter (`get_forecast_provider()`):** Controls only the retrieval source of the 6-hour forecast envelope (`MockForecastProvider` vs `LiveForecastProvider`).
2. **Deterministic Allocation Engine (`AllocationEngine.optimize()`):** Always runs the same constraint-satisfaction optimization and impact simulation model (`outcome_kind: "simulation"`), regardless of whether the forecast came from synthetic fixtures or the live partner API.
3. **Public Exposure Safeguard:** Live provider configuration does not alter frontend contracts or expose credentials.

---

## 10. Audit G — Test Quality & Independent Execution

### 10.1. Test Execution Results

Command executed from `backend/`:
```bash
../.venv/bin/python -m pytest -q
```
**Results:** **106 passed, 1 warning in 1.24s**

```
tests/api/test_allocations_api.py ...                                    [  2%]
tests/api/test_feedback_api.py ........                                  [ 10%]
tests/api/test_forecasts_api.py .......                                  [ 16%]
tests/api/test_health.py ..                                              [ 18%]
tests/api/test_reports_api.py .                                          [ 19%]
tests/api/test_scenarios_api.py .....                                    [ 24%]
tests/api/test_stations_api.py ...                                       [ 27%]
tests/integration/test_failures_and_infeasibility.py ....                [ 31%]
tests/integration/test_feedback_loop.py .                                [ 32%]
tests/integration/test_live_provider_client.py ......................... [ 55%]
......                                                                   [ 61%]
tests/integration/test_simulated_e2e_workflow.py ....                    [ 65%]
tests/integration/test_three_station_mock_integration.py ........        [ 72%]
tests/unit/test_constraints.py ..                                        [ 74%]
tests/unit/test_engine.py ....                                           [ 78%]
tests/unit/test_external_feedback_mapper.py .                            [ 79%]
tests/unit/test_forecast_validation.py .......                           [ 85%]
tests/unit/test_heuristics.py ..                                         [ 87%]
tests/unit/test_reports.py ..                                            [ 89%]
tests/unit/test_simulation.py ...                                        [ 92%]
tests/unit/test_station_mapper.py ........                               [100%]
```

**Deprecation Warning:**
`starlette/testclient.py:40: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.` (Standard third-party dependency deprecation, harmless).

### 10.2. Test Suite Coverage Analysis
- **Contract Parsing:** Tests verify nested `ForecastDetailRead` and `ForecastIntervalRead`.
- **Idempotency:** Tests cover HTTP 201 (new submission), HTTP 200 (identical retry with `is_duplicate: true`), and HTTP 409 (conflicting payload rejection).
- **Error Handling:** Tests cover timeout, HTTP 404, HTTP 401/403, and HTTP 5xx retry classification.
- **Boundaries:** Tests reject 30-second boundary deviations and verify timezone-equivalent UTC parsing.
- **End-to-End Simulation:** `test_simulated_e2e_integration_workflow` verifies all 6 workflow steps end-to-end with simulated contract responses.

---

## 11. Audit H — Git & Release Safety

- **Working Directory:** All changes are strictly confined to the feature branch `feature/predict-contract-alignment`.
- **Database Safety:** No local SQLite databases (`.db` / `.sqlite`) or migration state files are tracked.
- **Whitespace / Formatting:** `git diff --check` exited cleanly with code 0.
- **Deployment Infrastructure:** `render.yaml` specifies `PREDICT_PROVIDER_MODE=mock` as default, PostgreSQL managed database, Python 3.12.7 runtime, and correct static site build for the frontend.

---

## 12. Complete Ranked Audit Findings

| ID | Severity | Category | Title | Grounding File & Symbol | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **F-01** | **Critical** | Architecture | Circular import crash on `import app.services` | `backend/app/schemas/external_feedback.py:4` | Confirmed |
| **F-02** | **High** | Security | Live mode silently makes unauthenticated requests when token is missing | `backend/app/integrations/live_provider.py:58-60` | Confirmed |
| **F-03** | **High** | Business Logic | Partner HTTP 409 conflict swallowed into HTTP 201 by feedback service | `backend/app/services/feedback_service.py:234-237` | Confirmed |
| **F-04** | **Medium** | Observability | Bare `except Exception:` suppresses operational adjustment failures | `backend/app/services/feedback_service.py:170, 282` | Confirmed |
| **F-05** | **Medium** | Persistence | Ephemeral in-memory feedback ID mapping lost on backend restart | `backend/app/integrations/live_provider.py:38, 552` | Confirmed |
| **F-06** | **Medium** | Schema | `scenario_id` max_length discrepancy (64 vs 128 chars) | `backend/app/schemas/forecast.py:73, 173` | Confirmed |
| **F-07** | **Low** | Diagnostics | Error response bodies discarded in `create_forecast` and `get_forecast` | `backend/app/integrations/live_provider.py:108, 160` | Confirmed |
| **F-08** | **Low** | Database | Alembic migration 002 vs model constraint definition drift | `backend/alembic/versions/002_feedback_idempotency...` | Confirmed |
| **F-09** | **Informational** | Contract | Unimplemented partner endpoints (`/sessions`, `/stations`, `/feedback/{id}`) | `backend/app/integrations/live_provider.py` | Confirmed |

---

## 13. Detailed Finding Profiles

### Finding F-01: Circular Import Crash on `import app.services`
- **Severity:** Critical
- **Location:** [`backend/app/schemas/external_feedback.py:4`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/schemas/external_feedback.py#L4)
- **Code Evidence:**
  `from app.integrations.station_mapper import StationMapper` at line 4 of `external_feedback.py`.
- **Reproducibility:**
  Run `PYTHONPATH=backend .venv/bin/python -c "import app.services"`. Fails 100% of the time with:
  `ImportError: cannot import name 'AllocationIntervalInput' from partially initialized module 'app.schemas.external_feedback' (most likely due to a circular import)`.
- **Impact:** Any task, background worker, or script importing services directly crashes on startup.
- **Proposed Remediation:** Move `from app.integrations.station_mapper import StationMapper` inside `map_allocation_to_external_phase5()` at line 170 of `external_feedback.py`.

---

### Finding F-02: Live Mode Silently Makes Unauthenticated Requests When Token Is Missing
- **Severity:** High
- **Location:** [`backend/app/integrations/live_provider.py:58-60`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py#L58-L60)
- **Code Evidence:**
  ```python
  if self.service_token:
      headers["Authorization"] = f"Bearer {self.service_token}"
  return headers
  ```
- **Reproducibility:** Instantiate `LiveForecastProvider(service_token=None)` and call `get_forecast()`. The request sends no `Authorization` header.
- **Impact:** Fails late at the network layer with partner HTTP 401 instead of failing fast locally.
- **Proposed Remediation:** In `LiveForecastProvider._get_headers()`, check `if not self.service_token: raise ProviderIntegrationError("Predictor service token (PREDICT_SERVICE_TOKEN) is not configured for live mode.", is_retryable=False)`.

---

### Finding F-03: Partner HTTP 409 Conflict Swallowed into HTTP 201 by Feedback Service
- **Severity:** High
- **Location:** [`backend/app/services/feedback_service.py:234-237`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/feedback_service.py#L234-L237)
- **Code Evidence:**
  ```python
  except ProviderIntegrationError as pie:
      submission_status = "failed"
      error_details = pie.message
  except Exception as exc:
      submission_status = "failed"
      error_details = str(exc)
  ```
- **Reproducibility:** If `provider.submit_feedback(payload)` raises `IdempotencyConflictError`, `except Exception` catches it, sets `submission_status = "failed"`, and proceeds to return `FeedbackResponse` with status 201 Created.
- **Impact:** The client receives HTTP 201 instead of HTTP 409, violating API contract error semantics.
- **Proposed Remediation:** Catch and re-raise `IdempotencyConflictError` before the general `except Exception` block.

---

### Finding F-04: Bare `except Exception:` Suppresses Operational Adjustment Retrieval Failures
- **Severity:** Medium
- **Location:** [`backend/app/services/feedback_service.py:170, 282`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/feedback_service.py#L170)
- **Code Evidence:**
  ```python
  try:
      adj_response = provider.get_next_operational_adjustment(...)
  except Exception:
      adj_response = None
  ```
- **Impact:** Failures in retrieving operational adjustments produce no logs or diagnostic traces.
- **Proposed Remediation:** Import `logger` in `feedback_service.py`, log the exception, and record the failure reason in `AuditEvent.details_json`.

---

### Finding F-05: Ephemeral In-Memory Feedback ID Mapping Lost on Restart
- **Severity:** Medium
- **Location:** [`backend/app/integrations/live_provider.py:38, 552`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py#L38)
- **Code Evidence:** Mapping is stored in `_class_local_to_remote_feedback_ids: Dict[str, str] = {}`.
- **Impact:** If the service restarts before operational adjustments are queried, looking up `FBD-...` sends the local ID to EVCharge-Predict, resulting in HTTP 404.
- **Proposed Remediation:** Add fallback recovery looking up `OperationalAdjustment.calculation_assumptions_json` or `AuditEvent.details_json`. Plan a future migration adding `remote_feedback_id` to `FeedbackRecord`.

---

### Finding F-06: Schema Constraint Discrepancy on `scenario_id` (64 vs 128 chars)
- **Severity:** Medium
- **Location:** [`backend/app/schemas/forecast.py:73, 173`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/schemas/forecast.py#L73)
- **Code Evidence:** `scenario_id: str = Field(..., min_length=1, max_length=64)` in `forecast.py` vs `max_length=128` in OpenAPI and `external_feedback.py`.
- **Impact:** Partner scenario IDs longer than 64 chars will fail Pydantic validation.
- **Proposed Remediation:** Increase `max_length=128` in `ForecastDetailRead` and `ForecastAcknowledgement`.

---

## 14. Prioritized Remediation Plan

### Phase P0: Required Before Live Partner Testing
1. **Fix F-01:** Remove top-level `StationMapper` import from `backend/app/schemas/external_feedback.py` to eliminate circular import crash.
2. **Fix F-02:** Add fail-fast check in `LiveForecastProvider._get_headers()` when `self.service_token` is missing.
3. **Fix F-03:** Re-raise `IdempotencyConflictError` in `FeedbackService.submit_allocation_feedback()`.
4. **Environment:** Securely provision `PREDICT_SERVICE_TOKEN` in Render dashboard environment variables for `evcharge-opt-api`.

### Phase P1: Before Joint Acceptance Testing
1. **Fix F-04:** Add logging and audit tracking for operational adjustment retrieval failures in `FeedbackService`.
2. **Fix F-05:** Implement database fallback lookup for `remote_feedback_id` in `LiveForecastProvider`.
3. **Fix F-06:** Align `scenario_id` to `max_length=128` across `ForecastDetailRead` and `ForecastAcknowledgement`.
4. **Fix F-07:** Preserve response error text in `create_forecast` and `get_forecast`.

### Phase P2: Hardening & Cleanliness
1. **Fix F-08:** Align Alembic migration 002 with model definitions or add cleanup migration 003.
2. **Implement F-09:** Add pre-flight `/api/v1/sessions` data sufficiency check method to `LiveForecastProvider`.

---

## 15. Go / No-Go Checklist for Future Joint Live Testing

| Checklist Item | Current Status | Required Action Before Go |
| :--- | :--- | :--- |
| **All Backend Tests Passing** | **GO** (106 / 106 passed) | None |
| **Frontend Production Build Passing** | **GO** (Clean build) | None |
| **Git Working Tree Cleanliness** | **GO** (`git diff --check` clean) | None |
| **P0 Bug Fixes (F-01, F-02, F-03)** | **NO-GO** | Apply targeted fixes for F-01, F-02, F-03 |
| **Render `PREDICT_SERVICE_TOKEN` Provisioned** | **NO-GO** | Configure shared secret in Render Dashboard |
| **Station Mapping Safeguard Confirmed** | **CONDITIONAL** | Set `CONFIRM_PHYSICAL_STATION_MAPPINGS=true` for joint test |
| **Render Provider Mode Switched to Live** | **PENDING** | Set `PREDICT_PROVIDER_MODE=live` when ready for joint test |

---

## 16. Scope Limitations & Items Not Verified

1. **Live Partner API Network Calls:** In compliance with instructions, zero real outbound network calls were made to `https://evcharge-predict.onrender.com`. All partner interactions were verified via schema validation, mocked HTTP handlers, and simulated contracts.
2. **Physical Charger Hardware:** No real-world charging stations or Caltech site hardware were contacted or verified. Mappings remain `UNCONFIRMED_PROPOSAL`.
3. **Render Hosted Environment Secrets:** Live Render production environment variables were not inspected or altered; configuration was verified via `render.yaml` and repository settings.
