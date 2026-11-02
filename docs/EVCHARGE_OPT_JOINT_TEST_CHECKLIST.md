# EVCharge-Opt ↔ EVCharge-Predict Joint Integration Checklist & Partner Reconciliation

**Date:** October 28, 2026
**Workspace:** `/Users/bharanikumar.j/Documents/EVChargeOptimization`
**Git Branch:** `feature/predict-contract-alignment`
**Provider Mode:** `mock` (Default)
**Partner Status:** Partner teammate resolved local payload mismatch; 72 predictor backend tests passing; production secrets and ST-003 physical correspondence unconfirmed.

---

## 1. Executive Joint-Test Verdict

### Verdict: **NO-GO FOR LIVE PRODUCTION TESTING** / **GO FOR LOCAL SIMULATED JOINT TESTING**

* **Local EVCharge-Opt Codebase:** Fully compliant with partner contract. All **117 backend tests passed**, the frontend production build passed, schema validation matches contract specifications, and fail-fast safeguards are active.
* **Why Live Joint Testing Cannot Start Yet:**
  1. `PREDICT_SERVICE_TOKEN` has not yet been provisioned in the Render dashboard for `evcharge-opt-api`.
  2. Physical and logical correspondence for `ST-003` (Caltech source ID `1-39-139-652`) remains unconfirmed by the partner team.
  3. Production data sufficiency (< 5 sessions in trailing 21 days check) for `ST-003` is unverified in the predictor's production database.

EVCharge-Opt remains safely in **`mock` mode**.

---

## 2. Configuration & Invariant Audit

### 2.1. Provider Mode & Defaults
* **Configuration Source:** [`backend/app/core/config.py:24-63`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/core/config.py#L24-L63) & [`render.yaml:37-52`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/render.yaml#L37-L52)
* **Default Values:**
  * `PREDICT_PROVIDER_MODE = "mock"`
  * `PREDICT_API_BASE_URL = "http://127.0.0.1:8001"` (Local placeholder prevents unintended live egress)
  * `PREDICT_SERVICE_TOKEN = None`
  * `CONFIRM_PHYSICAL_STATION_MAPPINGS = False`
  * `STATION_INTEGRATION_PROFILE = "five_station_mock"`
  * `DEFAULT_DEFERRED_FRACTION = 0.70`
* **Provider Instantiation:** [`backend/app/integrations/__init__.py:10-14`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/__init__.py#L10-L14) returns [`MockForecastProvider`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/mock_provider.py) when `settings.is_mock_provider` is true. `MockForecastProvider` operates 100% offline with zero network calls and requires no service token.

### 2.2. Simulation-Mode Invariant
* **Separation of Ingestion and Allocation:** [`AllocationEngine.optimize()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/optimization/engine.py#L23-L37) is purely a local mathematical heuristic/LP constraint solver.
* **Immutable Outcome Kind:** In [`backend/app/services/allocation_service.py:191`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/allocation_service.py#L191) and [`backend/app/models/allocation.py:22`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/models/allocation.py#L22), `outcome_kind: "simulation"` is hardcoded for all runs.
* **Zero Actuation:** EVCharge-Opt contains **no hardware drivers, no OCPP protocol support, and no physical charger control**. Switching `PREDICT_PROVIDER_MODE=live` only changes the source of the 6-hour forecast envelope; it cannot command or switch physical chargers.

### 2.3. Station Mapping Gating
* **Gating Implementation:** [`backend/app/services/allocation_service.py:66-67`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/allocation_service.py#L66-L67) and [`backend/app/integrations/station_mapper.py:251-257`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/station_mapper.py#L251-L257).
* **Behavior:** When in live mode, any attempt to run allocation raises [`StationMappingError`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/core/exceptions.py#L56) unless `CONFIRM_PHYSICAL_STATION_MAPPINGS=true`.
* **Current Status:** All candidate mappings (`STN-01..03` $\to$ `ST-001..003`) remain classified as `UNCONFIRMED_PROPOSAL`.

---

## 3. Feedback Request Contract Specifications

EVCharge-Opt constructs the feedback submission matching EVCharge-Predict's `POST /api/v1/feedback` contract via [`LiveForecastProvider.submit_feedback()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py#L280):

### 3.1. Top-Level Payload (`PredictorFeedbackCreateRequest`)
* **`contract_version`:** `"1.0"` (String)
* **`allocation_run_id`:** e.g. `"ALC-1A2B3C4D"` (String, 1–128 chars; used as idempotency key on predictor side)
* **`forecast_id`:** e.g. `"fcst_20261028_01"` (String, 1–64 chars; matches originating forecast)
* **`scenario_id`:** e.g. `"scenario_default"` (String, 1–128 chars)
* **`submitted_at`:** ISO-8601 UTC timestamp (e.g. `"2026-10-28T08:00:00Z"`)
* **`optimizer_version`:** `"opt-core-1.0"` (String)
* **`stations`:** Non-empty list of station feedback items (`StationAllocationFeedbackInput`)

### 3.2. Station Feedback Container (`StationAllocationFeedbackInput`)
* **`station_id`:** Canonical predictor station ID (`"ST-001"`, `"ST-002"`, or `"ST-003"`) translated from internal IDs (`"STN-01"`, `"STN-02"`, `"STN-03"`) by [`StationMapper.to_external()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/station_mapper.py#L201).
* **`intervals`:** Consecutive hourly intervals (partial interval sets $\ge 1$ supported per documented partner contract).

### 3.3. Interval Item (`AllocationIntervalInput`)
* **`interval_start`:** Timezone-aware UTC start timestamp (matches originating forecast interval boundary).
* **`interval_end`:** Timezone-aware UTC end timestamp (matches originating forecast interval boundary).
* **`allocated_energy_kwh`:** Energy allocated by optimizer in **kWh** (Float $\ge 0.0$, strictly separated from vehicle arrivals; preserves `0.0` values).
* **`available_capacity_kw`:** Available power capacity in **kW** (Float $\ge 0.0$).
* **`reported_unmet_demand_kwh`:** Unserved energy demand in **kWh** (Float $\ge 0.0$; preserves `0.0` values).

---

## 4. Mocked Test Verification of Workflow Continuity

EVCharge-Opt's mocked integration tests ([`backend/tests/integration/test_simulated_e2e_workflow.py`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/tests/integration/test_simulated_e2e_workflow.py)) explicitly verify that the **same forecast ID** and the **correct remote feedback ID** are preserved throughout the complete workflow:

```
[Step 1] Ingest Forecast (fcst_contract_e2e_01)
       │
       ▼
[Step 2] Map Stations (ST-001..003 -> STN-01..03)
       │
       ▼
[Step 3] Interval 1 Allocation (ALC-INTERVAL-1)
       │
       ▼
[Step 4] Submit Feedback with forecast_id="fcst_contract_e2e_01"
       │  Predictor returns: feedback_id="fbk_e2e_contract_9988"
       ▼
[Step 5] Fetch Adjusted Demand:
       │  GET /api/v1/forecasts/fcst_contract_e2e_01/adjusted-demand?feedback_id=fbk_e2e_contract_9988
       ▼
[Step 6] Interval 2 Allocation uses operational_adjustment_id
          and parent_forecast_id="fcst_contract_e2e_01"
```

* **Forecast ID Continuity:** Verified in line 617, 659, and 674. If `parent_forecast_id` does not match the active forecast, [`AllocationService.run_allocation()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/allocation_service.py#L100-L105) rejects the adjustment.
* **Remote Feedback ID Continuity:** Verified in lines 351, 362, 634, and 656. The local feedback ID (`FBD-...`) is mapped to the partner's `fbk_...` remote ID, which is used for the `adjusted-demand` query.
* **Idempotency & Conflicts:** Verified in lines 614–648 (HTTP 200 on identical retry with `is_duplicate=True`; HTTP 409 on altered payload under same `allocation_run_id`).

---

## 5. Station ST-003 Evidence Requirements

`ST-003` is currently classified as `UNCONFIRMED_PROPOSAL`. Before `CONFIRM_PHYSICAL_STATION_MAPPINGS=true` can be safely enabled for joint testing, the following concrete evidence is required:

| Check Item | EVCharge-Opt Specification | EVCharge-Predict / Partner Specification | Required Evidence for Confirmation |
| :--- | :--- | :--- | :--- |
| **Physical Identity** | `"Suburban Retail Plaza"` (`STN-03`) | Canonical ID `"ST-003"` | Confirmation that Caltech ACN EVSE `1-39-139-652` represents the intended physical site. |
| **Charger Capacity** | 6 chargers $\times$ 50 kW = 300 kW nominal, 250 kW station limit | Model training profile for `ST-003` | Confirmation that predictor energy forecasts align with 6-charger 250 kW power envelope. |
| **Session Duration** | Average 45 minutes | Session history model | Confirmation that session duration assumptions are compatible. |
| **Historical Data Sufficiency** | Expects 6 valid hourly intervals | Requires $\ge 5$ sessions in trailing 21 days | Partner confirmation that EVCharge-Predict database has $\ge 5$ sessions for `1-39-139-652` so `/api/v1/forecasts` will not return HTTP 400 `InsufficientHistoryError`. |

---

## 6. Reconciliation Checklist: Local Evidence vs External Production Checks

### 6.1. Local Evidence Verified in EVCharge-Opt (100% Passed)
- [x] **Full Backend Test Suite:** 117 tests passing (`pytest backend/tests`).
- [x] **Frontend Production Build:** Built cleanly in 2.71s (`tsc && vite build`).
- [x] **Alembic Schema Alignment:** Zero drift (`alembic check` reports "No new upgrade operations detected").
- [x] **Circular Import:** Eliminated; fresh-process import verified.
- [x] **Fail-Fast Auth:** Raises non-retryable error if token is missing/empty before HTTP calls.
- [x] **HTTP 409 Propagation:** Re-raises `IdempotencyConflictError` as HTTP 409; never converted to 201.
- [x] **Durable ID Recovery:** Recovers `fbk_...` from `OperationalAdjustment` or `AuditEvent` across restarts.
- [x] **Unit Separation:** Energy in kWh is strictly separated from vehicle arrival counts.
- [x] **Numeric Fallback:** Explicit `is not None` checks preserve valid `0.0` values.
- [x] **Simulation Invariant:** `outcome_kind="simulation"` hardcoded; zero actuation paths exist.
- [x] **Station Safeguard:** Blocks live allocation when mappings are unconfirmed.
- [x] **Mock Mode Invariant:** Verified active by default in code and `render.yaml`.

### 6.2. External Production Checks (Requires Teammate / Deployment Owner)
- [ ] **E-01: Shared Secret Provisioning** — Configure `PREDICT_SERVICE_TOKEN` in Render for `evcharge-opt-api` matching `API_AUTH_TOKEN` on `evcharge-predict`.
- [ ] **E-02: Live Predictor Health** — Confirm `https://evcharge-predict.onrender.com/healthz` returns HTTP 200.
- [ ] **E-03: ST-003 Physical Agreement** — Partner team sign-off confirming Caltech `1-39-139-652` corresponds to `STN-03`.
- [ ] **E-04: Historical Data Sufficiency** — Verify predictor production DB has $\ge 5$ sessions in the last 21 days for `ST-001`, `ST-002`, and `ST-003`.
- [ ] **E-05: Render Environment Switch** — During scheduled live test window, update Render environment variables:
  * `PREDICT_PROVIDER_MODE=live`
  * `CONFIRM_PHYSICAL_STATION_MAPPINGS=true`
  * `STATION_INTEGRATION_PROFILE=three_station_integration`

---

## 7. Joint Integration Test Action Plan

When the partner team completes checks **E-01** through **E-04**:

1. **Step 1 (Pre-Flight):** Verify `GET /healthz` on both Render services.
2. **Step 2 (Baseline Forecast):** Call `POST /api/v1/forecasts` for `STN-01`, `STN-02`, `STN-03`; verify receipt of 6 consecutive hourly intervals.
3. **Step 3 (Interval 1 Simulation):** Run optimizer for Interval 1; verify power allocation satisfies residual grid limits.
4. **Step 4 (Feedback Submission):** Submit feedback for Interval 1; verify HTTP 201 response with predictor `fbk_...` ID.
5. **Step 5 (Idempotency Check):** Submit identical retry; verify HTTP 200 with `is_duplicate=true`.
6. **Step 6 (Adjusted Demand Ingestion):** Query `GET /api/v1/forecasts/{id}/adjusted-demand?feedback_id={fbk_...}`; verify operational demand envelope calculation.
7. **Step 7 (Interval 2 Allocation):** Run optimizer for Interval 2 using `operational_adjustment_id`; verify adjusted demand is utilized.
8. **Step 8 (Teardown):** Revert Render environment variables to `PREDICT_PROVIDER_MODE=mock`.
