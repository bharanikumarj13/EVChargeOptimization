# EVCharge-Opt API Contract & Integration Specification

Version: `v1.0.0`  
Base URL: `http://127.0.0.1:8002/api/v1`  
Interactive Swagger UI: `http://127.0.0.1:8002/docs`

---

## 1. System Health & Diagnostics

### `GET /healthz`
Service health check and database connectivity.
- **Response (200 OK):**
```json
{
  "status": "ok",
  "service": "EVCharge-Opt",
  "version": "0.1.0",
  "database": "healthy",
  "environment": "development"
}
```

### `GET /api/v1/integration/health`
Sanitized integration health. Redacts any credentials or secret service tokens.
- **Response (200 OK):**
```json
{
  "status": "healthy",
  "provider_mode": "mock",
  "is_mock": true,
  "configured_api_base_url": "http://127.0.0.1:8001",
  "last_successful_request": "2026-10-25T14:11:35Z",
  "feedback_delivery_status": "ready",
  "recent_errors": [],
  "service_version": "0.1.0",
  "environment": "development"
}
```

---

## 2. Infrastructure Endpoints

### `GET /api/v1/stations`
List all configured charging stations.
- **Query Params:** `active_only=true|false`
- **Response (200 OK):** List of `StationResponse` objects.

### `POST /api/v1/stations`
Register a new charging station.
- **Request Body:**
```json
{
  "station_id": "STN-06",
  "station_name": "Harbor Industrial Charging Depot",
  "charger_count": 6,
  "available_chargers": 6,
  "charger_power_kw_per_charger": 50.0,
  "station_power_limit_kw": 250.0,
  "avg_session_minutes": 40.0,
  "grid_group_id": "GRID-METRO",
  "is_active": true
}
```
- **Validation Rules:**
  - `available_chargers <= charger_count`
  - `charger_count >= 1`, `available_chargers >= 0`
  - `charger_power_kw_per_charger > 0`, `station_power_limit_kw > 0`
  - `grid_group_id` must reference an existing grid group.

### `POST /api/v1/stations/{station_id}/deactivate`
Deactivates a station, preventing power allocation.

### `GET /api/v1/grid-groups`
List shared substation grid groups with calculated `residual_capacity_kw`.

---

## 3. Allocation & Optimization Endpoints

### `POST /api/v1/allocations/run`
Executes the constraint-aware optimization algorithm for a scenario and interval.
- **Request Body:**
```json
{
  "scenario_id": "SCN-001",
  "forecast_id": "FC-001",
  "interval_start": "2026-10-26T08:00:00Z",
  "interval_end": "2026-10-26T09:00:00Z",
  "operational_adjustment_id": null
}
```
*Note:* When `operational_adjustment_id` is supplied, feedback-adjusted operational demand numbers are utilized for optimization instead of raw baseline forecast numbers.

- **Response (201 Created):**
```json
{
  "allocation_id": "ALC-D36E6F18",
  "scenario_id": "SCN-001",
  "forecast_id": "FC-001",
  "operational_adjustment_id": null,
  "interval_start": "2026-10-26T08:00:00Z",
  "interval_end": "2026-10-26T09:00:00Z",
  "status": "success",
  "outcome_kind": "simulation",
  "algorithm_version": "v1.0-priority-heuristic",
  "objective_description": "Hierarchical priority optimization...",
  "constraint_validation_passed": true,
  "warnings": [],
  "results": [
    {
      "station_id": "STN-01",
      "station_name": "Downtown Fast Charging Hub",
      "predicted_arrivals": 10.7,
      "predicted_energy_kwh": 235.4,
      "estimated_served": 10.7,
      "estimated_unserved": 0.0,
      "allocated_power_kw": 235.4,
      "estimated_served_energy_kwh": 235.4,
      "estimated_unserved_energy_kwh": 0.0,
      "estimated_wait_minutes": 15.9,
      "charger_utilization_pct": 89.2,
      "warnings": []
    }
  ],
  "created_at": "2026-10-25T14:11:35Z"
}
```

### `GET /api/v1/allocations/{allocation_id}`
Retrieves detailed station-wise allocation and impact results.

---

## 4. Feedback & Operational Adjustment Endpoints

### `POST /api/v1/allocations/{allocation_id}/feedback`
Creates a feedback record referencing the allocation and submits it to the forecast provider adapter.
- **Request Body (Optional):**
```json
{
  "deferred_fraction": 0.70,
  "idempotency_key": "IDEMP-ALC-D36E6F18-0.70"
}
```
- **Idempotency Guarantee:** If a feedback record matching `idempotency_key` already exists, the existing record and its linked operational adjustment are returned without duplicate submission.
- **Response (201 Created):**
```json
{
  "feedback_id": "FBD-7A685AAA",
  "scenario_id": "SCN-001",
  "forecast_id": "FC-001",
  "allocation_id": "ALC-D36E6F18",
  "outcome_kind": "simulation",
  "interval_start": "2026-10-26T08:00:00Z",
  "interval_end": "2026-10-26T09:00:00Z",
  "station_outcomes": [
    {
      "station_id": "STN-02",
      "predicted_arrivals": 17.1,
      "estimated_served": 10.0,
      "estimated_unserved": 7.1,
      "allocated_power_kw": 220.0,
      "estimated_wait_minutes": 93.9,
      "charger_utilization_pct": 100.0,
      "deferred_vehicles": 5.0,
      "deferred_energy_kwh": 77.8
    }
  ],
  "deferred_fraction": 0.7,
  "submission_status": "submitted",
  "idempotency_key": "IDEMP-ALC-D36E6F18-0.70",
  "retry_count": 0,
  "error_details": null,
  "operational_adjustment_id": "ADJ-B042A3AE",
  "created_at": "2026-10-25T14:11:35Z",
  "updated_at": "2026-10-25T14:11:35Z"
}
```

### `GET /api/v1/operational-adjustments/{operational_adjustment_id}`
Retrieves calculated subsequent-interval demand adjustments incorporating deferred unserved vehicles.

---

## 5. Reports & Audit Exports

### `GET /api/v1/reports/summary`
Returns system-wide aggregated operational KPIs.

### `GET /api/v1/reports/allocations.csv`
Streams spreadsheet-compatible CSV export.
- **Security Features:**
  - Formula injection mitigation (CWE-1236): Prepends `'` to cells starting with `=`, `+`, `-`, `@`, `\t`.
  - Path traversal & header injection mitigation: Filename sanitization.
