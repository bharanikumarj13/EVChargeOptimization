# EVCharge-Opt ↔ EVCharge-Predict Joint Integration Test Runbook

**Document Version:** 1.0
**Date:** October 28, 2026
**Status:** DRAFT / PRE-TEST PREPARATION
**System Under Test:**
- **EVCharge-Opt (Optimizer):** `https://evcharge-opt-api.onrender.com` (API), `https://evcharge-opt.onrender.com` (Frontend)
- **EVCharge-Predict (Predictor):** `https://evcharge-predict.onrender.com` (API)
**Workspace:** `/Users/bharanikumar.j/Documents/EVChargeOptimization`
**Git Branch:** `feature/predict-contract-alignment`
**Current Operating Mode:** `mock` (Offline, zero live external API traffic)

---

> [!IMPORTANT]
> **OPERATIONAL PREREQUISITES ARE CURRENTLY UNMET.**
> This runbook is a preparatory operational guide. It must **NOT** be executed against deployed production services until all preflight gates in Section 1 receive explicit, documented approval from both engineering leads. EVCharge-Opt remains strictly in `mock` mode.

---

## 1. Preflight Gates (Mandatory Go / No-Go Prerequisites)

All four preflight gates must be satisfied before scheduling or initiating live joint integration testing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PREFLIGHT GATES MATRIX                           │
├───────────────┬──────────────────────────────────┬─────────────┬────────────┤
│ Gate ID       │ Gate Description                 │ Target Svc  │ Status     │
├───────────────┼──────────────────────────────────┼─────────────┼────────────┤
│ GATE-01-AUTH  │ Shared Bearer Token Provisioned  │ Opt & Pred  │ UNMET      │
│ GATE-02-DATA  │ Production Data Sufficiency (>=5)│ Predictor   │ UNCONFIRMED│
│ GATE-03-STN   │ Physical Station Spec Sign-Off   │ Both Teams  │ UNCONFIRMED│
│ GATE-04-TIME  │ Coordinated Test Window Agreed   │ Both Teams  │ PENDING    │
└───────────────┴──────────────────────────────────┴─────────────┴────────────┘
```

### Gate 1: Authentication Configuration & Secret Exchange (`GATE-01-AUTH`)
* **Requirement:** A high-entropy shared secret must be securely generated and configured as an environment variable in both Render services by the authorized deployment owner:
  * EVCharge-Predict dashboard: `API_AUTH_TOKEN=<shared-secret>`
  * EVCharge-Opt dashboard: `PREDICT_SERVICE_TOKEN=<shared-secret>`
* **Evidence Required:** Independent confirmation by the authorized deployment owner that the secret is provisioned in the Render dashboard for both services.
* **Verification Security Rule:** Verification of credentials must occur solely via authenticated API requests (e.g. `POST /api/v1/forecasts`). Plaintext tokens, partial token fragments, or token hashes must **never** be shared, logged, or compared over team chat or unapproved communication channels.
* **Failure Condition:** If `PREDICT_SERVICE_TOKEN` is unset or empty, EVCharge-Opt's [`LiveForecastProvider._get_headers()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py#L58-L73) aborts immediately with a non-retryable `ProviderIntegrationError` before transmitting any network request.

### Gate 2: Production Historical-Data Sufficiency Check (`GATE-02-DATA`)
* **Requirement:** EVCharge-Predict's forecasting model requires historical charging session data to compute arrival distributions and energy demand. Per Section 5.7 of `EVCharge-Opt-Integration-Guide.md`, each station requires at least **5 completed charging sessions within the trailing 21-day window**.
* **Target Stations:**
  * `ST-001` (Caltech source: `1-39-139-650`)
  * `ST-002` (Caltech source: `1-39-139-651`)
  * `ST-003` (Caltech source: `1-39-139-652`)
* **Evidence Required:** The EVCharge-Predict operator must confirm historical data sufficiency directly (by querying the predictor's production database or calling the documented query endpoint `GET /api/v1/sessions?station_id=ST-00X&start_time=<UTC_ISO>&end_time=<UTC_ISO>`). EVCharge-Opt does not implement a client for `/api/v1/sessions`, nor does the contract support a `window_days` query parameter; this check is strictly an external predictor operator responsibility.
* **Failure Condition:** If any station has $< 5$ sessions in the trailing 21 days, EVCharge-Predict returns HTTP 400 with `InsufficientHistoryError`, causing forecast creation to fail.

### Gate 3: Physical & Logical Station Mapping & Capacity Sign-Off (`GATE-03-STN`)
* **Requirement:** Both engineering teams must confirm that the physical charger hardware and electrical envelopes correspond to the model's candidate mappings:
  * `STN-01` (Downtown Fast Hub) $\leftrightarrow$ `ST-001` $\leftrightarrow$ `1-39-139-650`: 8 chargers $\times$ 50 kW = 350 kW station cap.
  * `STN-02` (Tech Park Workplace) $\leftrightarrow$ `ST-002` $\leftrightarrow$ `1-39-139-651`: 10 chargers $\times$ 22 kW = 200 kW station cap.
  * `STN-03` (Suburban Retail Plaza) $\leftrightarrow$ `ST-003` $\leftrightarrow$ `1-39-139-652`: 6 chargers $\times$ 50 kW = 250 kW station cap.
* **Provisional Status:** Per Table 4.1 of `EVCharge-Opt-Integration-Guide.md`, `ST-003` is explicitly designated as **"Provisional & Unconfirmed. Authoritative hardware proof (serial number, nameplate, or utility interconnection log) is required before genuine charging sessions are ingested."** In EVCharge-Opt's [`StationMapper`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/station_mapper.py#L48-L53), `STN-03` remains `UNCONFIRMED_PROPOSAL`.
* **Evidence Required:** Authoritative hardware proof and mutual written sign-off from both teams confirming physical correspondence. No authoritative proof currently exists.
* **Failure Condition:** If `CONFIRM_PHYSICAL_STATION_MAPPINGS` remains `false` in live mode, EVCharge-Opt's [`AllocationService.run_allocation()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/services/allocation_service.py#L66-L67) raises `StationMappingError` and halts execution.

### Gate 4: Coordinated Test Window & Contact Protocol (`GATE-04-TIME`)
* **Requirement:** Both teams must agree on a synchronized UTC execution window (recommended: 30 minutes) during low-traffic periods.
* **Escalation Contacts:**
  * EVCharge-Opt Lead: On-call during test window.
  * EVCharge-Predict Lead: On-call during test window.

---

## 2. Configuration Checklist & Environment Variables

> [!CAUTION]
> **NEVER PASTE REAL SECRET VALUES INTO THIS RUNBOOK OR REPOSITORY FILES.**

The table below lists the required environment variables in the Render dashboard for the joint test window:

| Service | Environment Variable | Test-Window Value | Normal / Rollback Value | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **EVCharge-Opt** | `PREDICT_PROVIDER_MODE` | `live` | `mock` | Switches forecast provider from local fixtures to live partner API. |
| **EVCharge-Opt** | `PREDICT_API_BASE_URL` | `https://evcharge-predict.onrender.com` | `http://127.0.0.1:8001` | Live Render URL of partner predictor. |
| **EVCharge-Opt** | `PREDICT_SERVICE_TOKEN` | *[Configured Secret]* | *[Unset / None]* | Bearer token for partner endpoint authorization. |
| **EVCharge-Opt** | `CONFIRM_PHYSICAL_STATION_MAPPINGS` | `true` | `false` | Unlocks live allocation safeguard once Gate 3 is satisfied. |
| **EVCharge-Opt** | `STATION_INTEGRATION_PROFILE` | `three_station_integration` | `five_station_mock` | Scopes active stations to `STN-01`, `STN-02`, `STN-03`. |
| **EVCharge-Predict** | `API_AUTH_TOKEN` | *[Identical Secret]* | *[Production Secret]* | Authorizes incoming requests from EVCharge-Opt. |

### Architectural Guarantee: Ingestion vs Simulation Separation
* **Provider Mode (`PREDICT_PROVIDER_MODE`):** Controls **only** external HTTP I/O in [`LiveForecastProvider`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py).
* **Allocation Engine (`AllocationEngine.optimize`):** Remains strictly a **local mathematical simulation** (`outcome_kind: "simulation"`).
* **Zero Hardware Actuation:** EVCharge-Opt contains **no OCPP protocol handlers, no charging-station network clients, and no physical relay controls**. Switching to `live` mode cannot actuate real chargers.

---

## 3. Step-by-Step Execution Sequence

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      JOINT TEST EXECUTION FLOW                         │
 ├────────────────────────────────────────────────────────────────────────┤
 │                                                                        │
 │  Step 1: Health Diagnostic (GET /healthz on both services)             │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 2: Forecast Baseline Creation (POST /api/v1/forecasts)           │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 3: Forecast Horizon Ingestion & Schema Validation                │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 4: Interval 1 Simulation Optimization (Linear Programming)       │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 5: Feedback Submission (POST /api/v1/feedback)                   │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 6: Idempotency & Conflict Check (Retry HTTP 200 / Conflict 409)  │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 7: Adjusted Demand Retrieval (GET .../adjusted-demand)           │
 │          │                                                             │
 │          ▼                                                             │
 │  Step 8: Interval 2 Adjusted Allocation Optimization                   │
 │                                                                        │
 └────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Health Diagnostics
* **Action:** Check basic liveness of both services.
* **Commands / Requests:**
  ```bash
  curl -s -o /dev/null -w "%{http_code}" https://evcharge-predict.onrender.com/healthz
  curl -s -o /dev/null -w "%{http_code}" https://evcharge-opt-api.onrender.com/healthz
  ```
* **Acceptance Criteria:** Both return HTTP 200. Zero authentication headers are sent or required for `/healthz`.

### Step 2: Forecast Baseline Creation
* **Action:** Request a 6-hour baseline forecast from EVCharge-Predict for the three canonical stations.
* **Endpoint:** `POST https://evcharge-predict.onrender.com/api/v1/forecasts`
* **Request Headers:**
  * `Authorization: Bearer <PREDICT_SERVICE_TOKEN>`
  * `Content-Type: application/json`
* **Request Payload (`ForecastCreateRequest`):**
  ```json
  {
    "scenario_id": "joint_test_scenario_01",
    "station_ids": ["ST-001", "ST-002", "ST-003"],
    "forecast_start": "<TOP_OF_NEXT_HOUR_UTC_ISO>",
    "interval_minutes": 60,
    "horizon_intervals": 6
  }
  ```
* **Acceptance Criteria:** HTTP 201 Created. Response contains `forecast_id` (e.g. `fcst_...`), `status: "generated"`, `interval_minutes: 60`, `horizon_intervals: 6`.

### Step 3: Forecast Horizon Ingestion & Schema Validation
* **Action:** Retrieve full nested forecast intervals.
* **Endpoint:** `GET https://evcharge-predict.onrender.com/api/v1/forecasts/{forecast_id}`
* **Acceptance Criteria:** HTTP 200 OK. EVCharge-Opt parses `ForecastDetailRead`:
  * Exactly 3 stations (`ST-001`, `ST-002`, `ST-003`).
  * Exactly 6 consecutive 60-minute intervals per station.
  * Timestamps strictly UTC (`+00:00` or `Z`).
  * `predicted_arrivals` $\ge 0$ (vehicle count), `predicted_energy_kwh` $\ge 0.0$ (energy in kWh).

### Step 4: Interval 1 Simulation Optimization
* **Action:** Execute Interval 1 allocation in EVCharge-Opt.
* **Endpoint:** Internal `AllocationService.run_allocation()` / UI Allocation Run.
* **Parameters:**
  * `scenario_id`: `"joint_test_scenario_01"`
  * `forecast_id`: `{forecast_id}`
  * `interval_start`: `<INTERVAL_1_START_UTC>`
  * `interval_end`: `<INTERVAL_1_END_UTC>`
* **Acceptance Criteria:** Allocation status `"success"`, `constraint_validation_passed: true`, `outcome_kind: "simulation"`. Output includes allocated power and energy per station within physical transformer and charger ratings.

### Step 5: Feedback Submission
* **Action:** EVCharge-Opt posts allocation outcomes back to EVCharge-Predict.
* **Endpoint:** `POST https://evcharge-predict.onrender.com/api/v1/feedback`
* **Request Headers:**
  * `Authorization: Bearer <PREDICT_SERVICE_TOKEN>`
  * `Content-Type: application/json`
* **Request Payload (`PredictorFeedbackCreateRequest`):**
  ```json
  {
    "contract_version": "1.0",
    "allocation_run_id": "ALC-JOINT-01",
    "forecast_id": "{forecast_id}",
    "scenario_id": "joint_test_scenario_01",
    "submitted_at": "<CURRENT_UTC_ISO>",
    "optimizer_version": "opt-core-1.0",
    "stations": [
      {
        "station_id": "ST-001",
        "intervals": [
          {
            "interval_start": "<INTERVAL_1_START_UTC>",
            "interval_end": "<INTERVAL_1_END_UTC>",
            "allocated_energy_kwh": 85.5,
            "available_capacity_kw": 150.0,
            "reported_unmet_demand_kwh": 4.5
          }
        ]
      },
      {
        "station_id": "ST-002",
        "intervals": [
          {
            "interval_start": "<INTERVAL_1_START_UTC>",
            "interval_end": "<INTERVAL_1_END_UTC>",
            "allocated_energy_kwh": 55.0,
            "available_capacity_kw": 100.0,
            "reported_unmet_demand_kwh": 5.0
          }
        ]
      },
      {
        "station_id": "ST-003",
        "intervals": [
          {
            "interval_start": "<INTERVAL_1_START_UTC>",
            "interval_end": "<INTERVAL_1_END_UTC>",
            "allocated_energy_kwh": 40.0,
            "available_capacity_kw": 80.0,
            "reported_unmet_demand_kwh": 5.0
          }
        ]
      }
    ]
  }
  ```
* **Acceptance Criteria:** HTTP 201 Created. Response contains `feedback_id: "fbk_..."`, `is_duplicate: false`, `status: "accepted"`.

### Step 6: Idempotency & Conflict Verification
* **Action 6A (Identical Retry):** Re-submit the identical payload from Step 5 with the same `allocation_run_id: "ALC-JOINT-01"`.
  * **Expected:** HTTP 200 OK with `is_duplicate: true` and the original `feedback_id`.
* **Action 6B (Conflicting Payload):** Submit a differing payload (e.g. `allocated_energy_kwh: 999.0`) using the same `allocation_run_id: "ALC-JOINT-01"`.
  * **Expected:** HTTP 409 Conflict. Must propagate as HTTP 409 to callers (never 201).

### Step 7: Adjusted Demand Retrieval
* **Action:** Retrieve feedback-adjusted operational demand envelope for Interval 2.
* **Endpoint:** `GET https://evcharge-predict.onrender.com/api/v1/forecasts/{forecast_id}/adjusted-demand?feedback_id={feedback_id}`
* **Request Headers:** `Authorization: Bearer <PREDICT_SERVICE_TOKEN>`
* **Acceptance Criteria:** HTTP 200 OK. EVCharge-Opt parses `AdjustedDemandResponse`:
  * `feedback_id` matches the predictor remote feedback ID (`fbk_...`) returned in Step 5.
  * `forecast_id` matches `{forecast_id}`.
  * Stations contain Interval 2 boundaries (`target_interval_start`, `target_interval_end`).
  * `adjusted_operational_demand_kwh` reflects unserved demand carryover ($\max(\text{baseline}, \text{allocated})$).
  * Vehicle arrivals (`baseline_arrivals`) are strictly preserved without alteration.

### Step 8: Interval 2 Adjusted Allocation Optimization
* **Action:** Execute subsequent allocation for Interval 2 using the retrieved operational adjustment.
* **Endpoint:** Internal `AllocationService.run_allocation()`.
* **Parameters:**
  * `scenario_id`: `"joint_test_scenario_01"`
  * `forecast_id`: `{forecast_id}`
  * `interval_start`: `<INTERVAL_2_START_UTC>`
  * `interval_end`: `<INTERVAL_2_END_UTC>`
  * `operational_adjustment_id`: `"{operational_adjustment_id}"`
* **Acceptance Criteria:** Allocation status `"success"`, constraint validation passed, station demand inputs for STN-01..03 reflect the adjusted energy envelopes. Structured run audit event recorded.

---

## 4. Expected Results & Acceptance Criteria

| Protocol Step | Endpoint | HTTP Method | Expected Status | Critical Response Fields | Source of Truth / Evidence Status |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Health Check** | `/healthz` | `GET` | 200 | `{"status": "healthy"}` | Established in openapi_schema.json |
| **Forecast Creation** | `/api/v1/forecasts` | `POST` | 201 | `forecast_id` (`fcst_...`), `status`, `horizon_intervals: 6` | Integration Guide Sec. 5.1 |
| **Forecast Retrieval**| `/api/v1/forecasts/{id}` | `GET` | 200 | `stations` (3 items), nested `intervals` (6 items each), UTC ISO timestamps | Integration Guide Sec. 5.2 |
| **Feedback Initial** | `/api/v1/feedback` | `POST` | 201 | `feedback_id` (`fbk_...`), `is_duplicate: false`, `status: "accepted"` | Integration Guide Sec. 5.3 (*Note: OpenAPI omits 201 body schema; Guide defines FeedbackCreateResponse*) |
| **Feedback Retry** | `/api/v1/feedback` | `POST` | 200 | `feedback_id` (identical), `is_duplicate: true` | Integration Guide Sec. 5.3 |
| **Feedback Conflict**| `/api/v1/feedback` | `POST` | 409 | `detail` with conflict description | Integration Guide Sec. 5.3 |
| **Adjusted Demand** | `/api/v1/forecasts/{id}/adjusted-demand` | `GET` | 200 | `feedback_id`, `stations`, `adjusted_operational_demand_kwh` | Integration Guide Sec. 5.5 |

### Discrepancy & Confirmation Call-Outs:
1. **OpenAPI vs Integration Guide 201 Response Body (Verified Fact vs Generator Omission):**
   * *Status:* Verified contract fact. Section 5.3 of `EVCharge-Opt-Integration-Guide.md` explicitly documents that an initial feedback submission returning `HTTP 201 Created` returns a JSON `FeedbackCreateResponse` with `is_duplicate: false`. The published `openapi_schema.json` omitted the `content` dictionary on `201` (a known OpenAPI generator artifact) while defining it under `200` (`$ref: #/components/schemas/FeedbackCreateResponse`). EVCharge-Opt's client ([`LiveForecastProvider.submit_feedback()`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/app/integrations/live_provider.py#L561)) parses `FeedbackCreateResponse` on both 201 and 200, which is thoroughly verified by mocked tests ([`test_live_provider_submit_feedback_http_201_success`](file:///Users/bharanikumar.j/Documents/EVChargeOptimization/backend/tests/integration/test_live_provider_client.py#L225)). Teammate confirmation in the joint session is only needed to verify that the deployed predictor version running on Render contains the fixed response.
2. **Pre-flight Historical Data Sufficiency (`GET /api/v1/sessions`):**
   * *Status:* Documented parameters verified. Neither `openapi_schema.json` nor the Integration Guide defines a `window_days` parameter. The documented query parameters are `station_id`, `start_time`, `end_time`, `limit`, and `offset`. Because EVCharge-Opt's client does not implement or invoke `/api/v1/sessions`, historical data sufficiency ($\ge 5$ sessions in trailing 21 days) cannot be confirmed by EVCharge-Opt and must be confirmed directly by the EVCharge-Predict operator (via database query or curl).

---

## 5. Evidence Log Template

Use the following template to record execution evidence during the joint test.

> [!WARNING]
> **NEVER LOG AUTHORIZATION HEADERS, BEARER TOKENS, OR CREDENTIALS IN THIS LOG.**

```markdown
### Joint Test Execution Evidence Log
- **Date & UTC Time:** _________________________
- **EVCharge-Opt Operator:** _________________________
- **EVCharge-Predict Operator:** _________________________
- **Agreed Shared Correlation / Scenario ID:** _________________________

| Step # | Timestamp (UTC) | Endpoint / Action | Sent Identifier(s) | HTTP Status | Returned ID(s) | Validation Outcome | Notes / Error Text |
| :---: | :---: | :--- | :--- | :---: | :--- | :---: | :--- |
| **1** | __:__:__ | `GET /healthz` (Predict) | N/A | [ ] 200 | N/A | PASS / FAIL | |
| **1b**| __:__:__ | `GET /healthz` (Opt) | N/A | [ ] 200 | N/A | PASS / FAIL | |
| **2** | __:__:__ | `POST /api/v1/forecasts` | ST-001..003 | [ ] 201 | `forecast_id`: ________ | PASS / FAIL | |
| **3** | __:__:__ | `GET /api/v1/forecasts/{id}` | `forecast_id`: ________ | [ ] 200 | Intervals: 6 per station | PASS / FAIL | |
| **4** | __:__:__ | Interval 1 Optimization | Scenario: ________ | N/A | Status: success | PASS / FAIL | LP solver passed |
| **5** | __:__:__ | `POST /api/v1/feedback` | `allocation_run_id`: ________ | [ ] 201 | `feedback_id`: ________ | PASS / FAIL | `is_duplicate: false` |
| **6a**| __:__:__ | Feedback Retry (Identical) | `allocation_run_id`: ________ | [ ] 200 | `feedback_id`: ________ | PASS / FAIL | `is_duplicate: true` |
| **6b**| __:__:__ | Feedback Retry (Differing) | `allocation_run_id`: ________ | [ ] 409 | Error: Conflict | PASS / FAIL | Rejection verified |
| **7** | __:__:__ | `GET .../adjusted-demand` | `feedback_id`: ________ | [ ] 200 | Adjusted kWh parsed | PASS / FAIL | Envelope derived |
| **8** | __:__:__ | Interval 2 Optimization | `adj_id`: ________ | N/A | Status: success | PASS / FAIL | Adjusted load used |
```

---

## 6. Failure Handling & Abort Conditions

If an anomaly occurs, identify the failure category below and apply the safe immediate action:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FAILURE HANDLING MATRIX                            │
├────────────────────┬───────────┬────────────────────────────────────────────┤
│ Failure Category   │ HTTP Code │ Immediate Safe Action                      │
├────────────────────┼───────────┼────────────────────────────────────────────┤
│ Authentication     │ 401 / 403 │ STOP IMMEDIATELY. Verify Render tokens.    │
│ History Deficiency │ 400       │ STOP. Insufficient session history in DB.  │
│ Station Safeguard  │ N/A (422) │ STOP. Physical mapping unconfirmed.        │
│ Schema Deviation   │ 422       │ Log payload diff; abort run.               │
│ Unexpected 409     │ 409       │ Verify allocation_run_id uniqueness.       │
│ Network Timeout    │ 504 / 502 │ Single retry (10s backoff); abort if persists│
│ Missing Adjustment │ 404       │ Verify remote feedback_id matches fbk_... │
└────────────────────┴───────────┴────────────────────────────────────────────┘
```

1. **Authentication Failure (HTTP 401 / 403):**
   * *Cause:* `PREDICT_SERVICE_TOKEN` does not match EVCharge-Predict's `API_AUTH_TOKEN`, is expired, or header format is malformed.
   * *Action:* **STOP TEST IMMEDIATELY.** Do not retry in a loop. Authorized deployment owners must independently inspect the Render dashboard environment variables for both services in private. Do not transmit, log, or paste plaintext secrets, token fragments, or token hashes into team chat or unapproved channels.
2. **Insufficient Historical Data (HTTP 400 `InsufficientHistoryError`):**
   * *Cause:* One or more stations has $< 5$ charging sessions in the trailing 21-day window.
   * *Action:* **ABORT TEST.** Predictor team must seed or populate historical session data for Caltech EVSEs `1-39-139-650..652`.
3. **Station Mapping Safeguard Error (`StationMappingError`):**
   * *Cause:* Attempted live allocation while `CONFIRM_PHYSICAL_STATION_MAPPINGS` is `false`, or station ID outside `ST-001..003`.
   * *Action:* Verify that Gate 3 was formally satisfied and `CONFIRM_PHYSICAL_STATION_MAPPINGS=true` is set.
4. **Timestamp or Boundary Mismatch (HTTP 422 / `InvalidForecastError`):**
   * *Cause:* Submitted feedback interval timestamps differ from the originating forecast interval boundaries.
   * *Action:* Log the exact timestamp strings; verify that `forecast_start` was strictly aligned to top-of-hour (`:00:00Z`).
5. **Unexpected HTTP 409 Conflict:**
   * *Cause:* `allocation_run_id` was previously used by another test execution with a different payload.
   * *Action:* Generate a fresh unique `allocation_run_id` (e.g. `ALC-JOINT-<UUID>`) and re-test.
6. **Network Timeout / Connection Error (HTTP 502 / 503 / 504):**
   * *Cause:* Render service spinning up (cold start) or network partition.
   * *Action:* Allow 10-second cool-down for Render free/starter instance spin-up; perform one retry of `/healthz`. If unrecovered, abort.
7. **Missing Adjusted Demand (HTTP 404):**
   * *Cause:* Querying adjusted demand with the local ID (`FBD-...`) instead of the partner predictor ID (`fbk_...`), or feedback processing was delayed.
   * *Action:* Check Step 5 response; ensure the query uses the exact `feedback_id` value returned by the predictor.

---

## 7. Rollback & Post-Test Cleanup

Immediately upon test completion (or upon hitting an abort condition), execute the rollback procedure to return EVCharge-Opt to safe isolation:

### Step 7.1: Revert Render Environment Variables
In the Render dashboard for `evcharge-opt-api`:
1. Set `PREDICT_PROVIDER_MODE=mock`.
2. Set `CONFIRM_PHYSICAL_STATION_MAPPINGS=false`.
3. Set `STATION_INTEGRATION_PROFILE=five_station_mock`.
4. Set `PREDICT_API_BASE_URL=http://127.0.0.1:8001`.
5. Remove or clear `PREDICT_SERVICE_TOKEN`.
6. Trigger a deployment / restart to apply the reverted configuration.

### Step 7.2: Database Safety Guarantee
* **NO DESTRUCTIVE DDL / MIGRATIONS:** Do not drop tables, run `alembic downgrade`, or truncate tables.
* **Audit Trail Preservation:** All `AllocationRun`, `FeedbackRecord`, and `AuditEvent` records created during the test are preserved with `outcome_kind="simulation"`. These records provide an immutable audit trail for post-test analysis and do not interfere with standard operations.

### Step 7.3: Health Verification of Reverted State
Run local or root health checks:
```bash
curl https://evcharge-opt-api.onrender.com/healthz
curl https://evcharge-opt-api.onrender.com/api/v1/integration/health
```
* **Acceptance:** `/integration/health` reports `provider_mode: "mock"`, `status: "healthy"`.

---

## 8. Final Sign-Off & Approvals

Both leads must independently review the executed evidence log before certifying the joint integration test.

### EVCharge-Predict Lead Sign-Off
- [ ] Forecast creation & retrieval completed under documented contract.
- [ ] Feedback ingestion verified with correct station ID mapping.
- [ ] Duplicate retry (HTTP 200) and conflict rejection (HTTP 409) verified.
- [ ] Adjusted operational demand derived and transmitted correctly.
- **Signed:** _____________________________________
- **Date:** _______________________________________

### EVCharge-Opt Lead Sign-Off
- [ ] 6-hour baseline forecast parsed into internal data structures.
- [ ] Linear programming optimization satisfied power and grid limits.
- [ ] Feedback reported without units corruption (kWh separated from vehicle counts).
- [ ] Remote feedback ID continuity maintained through adjusted demand retrieval.
- [ ] Subsequent interval optimization executed with adjusted load envelope.
- [ ] Safe rollback to mock mode verified.
- **Signed:** _____________________________________
- **Date:** _______________________________________
