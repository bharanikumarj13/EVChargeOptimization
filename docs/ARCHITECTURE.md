# EVCharge-Opt System Architecture & Technical Specification

## 1. Executive Summary

**EVCharge-Opt** (Intelligent EV Charging Allocation and Optimization System) is designed to operate in tandem with an external prediction service (**EVCharge-Predict**). It receives 6-interval charging demand forecasts (arrival counts and cumulative energy requirements in kWh), validates station hardware limits and shared electrical grid capacities, determines deterministic resource allocations, estimates service quality and queue delays, and generates feedback records that produce downstream operational adjustments for subsequent planning horizons.

---

## 2. Logical Architecture

```mermaid
flowchart TD
    subgraph Client ["Frontend Layer (127.0.0.1:5174)"]
        UI["React 18 / TypeScript Dashboard"]
        Store["Typed API Client"]
    end

    subgraph ServiceLayer ["FastAPI Application Services (127.0.0.1:8002)"]
        Router["Versioned API Routers (/api/v1)"]
        AllocSvc["Allocation Service"]
        FeedSvc["Feedback Service"]
        RepSvc["Reporting & Export Service"]
        Engine["Optimization Engine (Priority Heuristic)"]
        Sim["Impact Simulation Module"]
    end

    subgraph Adapters ["Integration Layer"]
        AdapterBase["ForecastProviderAdapter (ABC)"]
        MockAdapter["MockForecastProvider (Deterministic Offline Fixtures)"]
        LiveAdapter["LiveForecastProvider (HTTPX + Bearer Auth)"]
    end

    subgraph Persistence ["Persistence Layer"]
        Repo["SQLAlchemy 2.0 Repositories"]
        DB[("PostgreSQL / SQLite Storage")]
        Alembic["Alembic Schema Migrations"]
    end

    subgraph External ["External Service (Partner)"]
        PartnerAPI["EVCharge-Predict REST API"]
    end

    UI --> Store
    Store --> Router
    Router --> AllocSvc
    Router --> FeedSvc
    Router --> RepSvc

    AllocSvc --> Engine
    Engine --> Sim
    AllocSvc --> AdapterBase
    FeedSvc --> AdapterBase
    
    AdapterBase -.-> MockAdapter
    AdapterBase -.-> LiveAdapter
    LiveAdapter -.-> PartnerAPI

    AllocSvc --> Repo
    FeedSvc --> Repo
    RepSvc --> Repo
    Repo --> DB
```

---

## 3. Mathematical & Optimization Formulation

### 3.1 Hard Constraints

For each station $s \in \mathcal{S}$ and shared grid group $g \in \mathcal{G}$, let:
- $C_s$: installed chargers ($C_s \ge 1$)
- $A_s$: available operational chargers ($0 \le A_s \le C_s$)
- $P_s^{\text{rate}}$: rated power per charger ($kW$)
- $P_s^{\text{limit}}$: station service entrance limit ($kW$)
- $P_s^{\text{alloc}}$: power allocated to station $s$ ($kW$)
- $L_g^{\text{limit}}$: total grid feeder capacity ($kW$)
- $L_g^{\text{base}}$: baseline non-EV electrical load ($kW$)
- $\Delta t$: planning interval duration in hours ($\Delta t = \text{interval\_minutes} / 60.0$)

**Mandatory Feasibility Constraints:**
1. Non-negativity:
   $$P_s^{\text{alloc}} \ge 0, \quad \forall s \in \mathcal{S}$$
2. Inactive Stations:
   $$P_s^{\text{alloc}} = 0, \quad \text{if } s \text{ is inactive or } A_s = 0$$
3. Station Physical Power Cap:
   $$P_s^{\text{alloc}} \le \min\left(P_s^{\text{limit}}, A_s \times P_s^{\text{rate}}\right), \quad \forall s \in \mathcal{S}$$
4. Shared Substation Residual Grid Feeder Limit:
   $$\sum_{s \in \mathcal{S}_g} P_s^{\text{alloc}} \le \max\left(0, L_g^{\text{limit}} - L_g^{\text{base}}\right), \quad \forall g \in \mathcal{G}$$

### 3.2 Turnover & Feasible Served Vehicles

Let:
- $D_s^{\text{arrivals}}$: forecasted or adjusted arrival vehicles.
- $D_s^{\text{energy}}$: forecasted energy demand ($kWh$).
- $\tau_s$: average charging session duration in minutes.

The physical vehicle turnover capacity of the station over interval $\Delta t$ is:
$$\text{Cap}_s^{\text{phys}} = A_s \times \left(\frac{\Delta t \times 60}{\tau_s}\right)$$

The maximum vehicle throughput enabled by the allocated power is:
$$\text{Cap}_s^{\text{energy}} = \frac{P_s^{\text{alloc}} \times \Delta t}{\bar{e}_s}, \quad \text{where } \bar{e}_s = \frac{D_s^{\text{energy}}}{D_s^{\text{arrivals}}}$$

Feasible served vehicles:
$$V_s^{\text{served}} = \min\left(D_s^{\text{arrivals}}, \text{Cap}_s^{\text{phys}}, \text{Cap}_s^{\text{energy}}\right)$$
$$V_s^{\text{unserved}} = \max\left(0, D_s^{\text{arrivals}} - V_s^{\text{served}}\right)$$

Conservation of Demand:
$$V_s^{\text{served}} + V_s^{\text{unserved}} \equiv D_s^{\text{arrivals}}$$

---

## 4. Impact Simulation Metrics

### 4.1 Queue Waiting Time Approximation
When demand is within physical turnover capacity ($D_s \le \text{Cap}_s^{\text{phys}}$), queue delay follows a non-linear turnover load function:
$$W_s = \left(\frac{\tau_s}{2}\right) \times \left(\frac{D_s^{\text{arrivals}}}{\text{Cap}_s^{\text{phys}}}\right)^2$$
When arrival rate exceeds turnover capacity ($D_s > \text{Cap}_s^{\text{phys}}$):
$$W_s = 0.5 \tau_s + 1.5 \tau_s \times \left(\frac{D_s^{\text{arrivals}} - \text{Cap}_s^{\text{phys}}}{D_s^{\text{arrivals}}}\right)$$
Results are bounded and clearly labeled as **simulated estimates**.

### 4.2 Charger Utilization
Calculated as the ratio of occupied plug-minutes to available plug-minutes:
$$U_s = \frac{V_s^{\text{served}} \times \tau_s}{A_s \times \Delta t \times 60} \times 100\%$$

---

## 5. Feedback Loop & Adjustment Lineage

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant Optimizer as EVCharge-Opt Engine
    participant DB as Persistence Layer
    participant Adapter as Forecast Provider Adapter
    participant Predictor as EVCharge-Predict (Mock / Live)

    Operator->>Optimizer: Run Allocation (Interval 1)
    Optimizer->>DB: Fetch Station & Grid Config
    Optimizer->>Adapter: Fetch Baseline Forecast Snapshot
    Optimizer->>Optimizer: Validate Constraints & Solve Priority Allocation
    Optimizer->>DB: Persist AllocationRun & AllocationResult
    Optimizer-->>Operator: Display Allocation Results & Telemetry

    Operator->>Optimizer: Submit Allocation Feedback (fraction=0.70)
    Optimizer->>DB: Check Idempotency Key (Return cached if duplicate)
    Optimizer->>Adapter: POST Feedback Payload
    Adapter->>Predictor: Deliver Outcomes (Served, Unserved, Wait)
    Predictor-->>Adapter: Acknowledgment
    Optimizer->>Adapter: Request Next-Interval Operational Adjustment
    Adapter-->>Optimizer: Return OperationalAdjustment Payload
    Optimizer->>DB: Persist OperationalAdjustment Record
    Optimizer-->>Operator: Display Updated Feedback Lineage

    Operator->>Optimizer: Run Subsequent Allocation (Interval 2) with Adjustment ID
    Optimizer->>DB: Load OperationalAdjustment (Adjusted Demand)
    Optimizer->>Optimizer: Optimize using Adjusted Demand (No Double Counting)
    Optimizer->>DB: Persist Subsequent Allocation Linked to Parent Lineage
```

---

## 6. Database Entity-Relationship Diagram

```mermaid
erDiagram
    GRID_GROUPS ||--o{ STATIONS : "serves"
    SCENARIOS ||--o{ ALLOCATION_RUNS : "contains"
    ALLOCATION_RUNS ||--o{ ALLOCATION_RESULTS : "yields"
    ALLOCATION_RUNS ||--o{ FEEDBACK_RECORDS : "generates"
    FEEDBACK_RECORDS ||--o| OPERATIONAL_ADJUSTMENTS : "derives"
    SCENARIOS ||--o{ FORECAST_SNAPSHOTS : "snapshots"

    GRID_GROUPS {
        string grid_group_id PK
        string grid_group_name
        float grid_limit_kw
        float other_load_kw
        datetime created_at
    }

    STATIONS {
        string station_id PK
        string station_name
        int charger_count
        int available_chargers
        float charger_power_kw_per_charger
        float station_power_limit_kw
        float avg_session_minutes
        string grid_group_id FK
        bool is_active
    }

    ALLOCATION_RUNS {
        string allocation_id PK
        string scenario_id FK
        string forecast_id
        string operational_adjustment_id
        datetime interval_start
        datetime interval_end
        string status
        string outcome_kind
        bool constraint_validation_passed
    }

    ALLOCATION_RESULTS {
        int id PK
        string allocation_id FK
        string station_id
        float predicted_arrivals
        float predicted_energy_kwh
        float estimated_served
        float estimated_unserved
        float allocated_power_kw
        float charger_utilization_pct
        float estimated_wait_minutes
    }

    FEEDBACK_RECORDS {
        string feedback_id PK
        string allocation_id FK
        string forecast_id
        float deferred_fraction
        string submission_status
        string idempotency_key UK
    }

    OPERATIONAL_ADJUSTMENTS {
        string operational_adjustment_id PK
        string source_feedback_id FK
        string parent_forecast_id
        datetime target_interval_start
        datetime target_interval_end
        text station_adjustments_json
    }
```
