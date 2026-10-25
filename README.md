# EVCharge-Opt — Intelligent EV Charging Allocation and Optimization System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.4-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3.1-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6.3-3178C6?logo=typescript)](https://www.typescriptlang.org)
[![Python 3.12](https://img.shields.io/badge/Python-3.12.0-3776AB?logo=python)](https://www.python.org)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-3.4.14-38B2AC?logo=tailwindcss)](https://tailwindcss.com)

**EVCharge-Opt** is an enterprise-grade, constraint-aware EV charging allocation and optimization platform. It ingests arrival and energy demand forecasts from an external prediction system (**EVCharge-Predict**), allocates charging resources under strict station hardware and shared substation grid limits, calculates operational outcomes (served vehicles, unserved backlog, queue wait times, and charger utilization), and delivers closed-loop allocation feedback to compute deferred operational demand adjustments.

---

## ⚡ Key Capabilities

1. **Strict Hardware & Grid Constraint Enforcement**
   - Individual charger power ratings & installed charger counts.
   - Station-level power limits ($kW$).
   - Shared substation grid group capacities with non-EV baseline load accounting:
     $$\text{residual\_grid\_capacity\_kw} = \max(0, \text{grid\_limit\_kw} - \text{other\_load\_kw})$$
   - Hard physical limits guaranteed across multi-station shared feeders.

2. **Deterministic Priority Optimization Algorithm**
   - Hierarchical objective: (1) Maximize feasible arrivals served; (2) Satisfy charger and substation ratings; (3) Respect shared residual grid limits; (4) Minimize waiting time; (5) Balance grid loading.
   - Deterministic tie-breaking ensures identical inputs yield identical outputs.

3. **Closed-Loop Feedback Adapter & Adjustment Lineage**
   - Ingestion of 6-interval demand forecasts via pluggable Provider Adapter (`Mock` or `Live` HTTP).
   - Generates feedback records referencing source allocations.
   - Authoritative operational demand adjustment calculation for subsequent intervals based on deferred unserved demand fractions.
   - **Baseline Immutability**: The original forecast snapshot remains 100% immutable; operational adjustments are stored as distinct child records.
   - **Database-Backed Idempotency**: Duplicate feedback submissions are deduplicated using database-level uniqueness constraints.

4. **Professional Dark-First Operator Dashboard**
   - Built with React 18, TypeScript, Tailwind CSS, Lucide icons, and Recharts.
   - 7 functional pages: Overview, Run Optimization, Stations & Grid, Allocation Results, Feedback Loop, History & Reports, Integration Health.
   - Real spreadsheet-safe CSV exports with formula injection (CWE-1236) mitigations.

---

## 🛠️ Architecture & Port Mappings

```
Operator (Browser) -> React Frontend (http://127.0.0.1:5174)
                          | (REST / JSON)
                          v
FastAPI Backend (http://127.0.0.1:8002)
   ├── Optimization Engine (Priority Heuristic)
   ├── Simulation Engine (Queuing & Utilization)
   ├── Forecast Provider Adapter (Mock offline / Live HTTPX)
   └── Persistence Layer (SQLAlchemy 2.0 + Alembic)
            |
            v
   Database (SQLite local fallback / PostgreSQL production)
```

- **Frontend:** `http://127.0.0.1:5174`
- **Backend API:** `http://127.0.0.1:8002`
- **Interactive Swagger Documentation:** `http://127.0.0.1:8002/docs`
- **Health Check Endpoint:** `http://127.0.0.1:8002/healthz`

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python:** 3.12.x
- **Node.js:** 22.x (`npm 10.x`)

### macOS / Linux Setup
```bash
# 1. Clone or navigate to the workspace
cd /Users/bharanikumar.j/Documents/EVChargeOptimization

# 2. Setup Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# 3. Apply Alembic Database Migrations & Seed Baseline Data
cd backend
../.venv/bin/alembic upgrade head
cd ..
./.venv/bin/python backend/scripts/seed_data.py

# 4. Start the Backend API Server
./.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8002

# 5. In a separate terminal, install and start the Frontend
cd frontend
npm install
npm run dev
# Accessible at http://127.0.0.1:5174
```

### Windows (PowerShell) Setup
```powershell
# 1. Navigate to project root
cd C:\path\to\EVChargeOptimization

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt

# 3. Run database migrations & seed baseline data
cd backend
..\.venv\Scripts\alembic.exe upgrade head
cd ..
.\.venv\Scripts\python.exe backend\scripts\seed_data.py

# 4. Start Backend
.\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --host 127.0.0.1 --port 8002

# 5. In a separate terminal, install and start Frontend
cd frontend
npm install
npm run dev
```

---

## 🧪 Automated Testing & Verification

Run the full pytest backend test suite (unit, API, and integration tests):
```bash
./.venv/bin/pytest backend/tests
```

Run the end-to-end programmatic feedback loop verification demo:
```bash
./.venv/bin/python backend/scripts/run_feedback_loop_demo.py
```

Run frontend type checks and production build:
```bash
cd frontend && npm run build
```

---

## 📚 Comprehensive Documentation

- [System Architecture & Optimization Formulation](docs/ARCHITECTURE.md)
- [API Contract & Schema Specification](docs/API_CONTRACT.md)
- [macOS Installation & Run Instructions](docs/SETUP_MACOS.md)
- [Windows PowerShell Setup Guide](docs/SETUP_WINDOWS.md)
- [Render Cloud Deployment Guide](docs/RENDER_DEPLOYMENT.md)
- [Engineering Readiness & Acceptance Report](docs/READINESS_REPORT.md)
