# macOS Setup & Development Guide

This guide describes how to run and test **EVCharge-Opt** locally on macOS (tested on Apple Silicon with Python 3.12.0 and Node.js 22.22.0).

---

## 1. Prerequisites Check

In your macOS terminal, verify the installed runtimes:
```bash
python3 --version   # Python 3.12.x
node --version      # v22.x
npm --version       # 10.x
```

---

## 2. Backend Setup & Startup

All operations must be run from inside the project directory:
```bash
cd /Users/bharanikumar.j/Documents/EVChargeOptimization
```

### 2.1 Virtual Environment
```bash
# Create local virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip and install pinned backend dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2.2 Database Initialization & Migrations
By default, the backend uses a local SQLite database (`evcharge_opt.db`) requiring zero external dependencies:
```bash
# Apply schema migrations via Alembic
cd backend
../.venv/bin/alembic upgrade head
cd ..

# Seed default baseline stations, grid groups, and scenario
./.venv/bin/python backend/scripts/seed_data.py
```

### 2.3 Start FastAPI Backend
```bash
./.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8002 --reload
```
- API is running at: `http://127.0.0.1:8002`
- Interactive Swagger documentation: `http://127.0.0.1:8002/docs`
- Health check: `http://127.0.0.1:8002/healthz`

---

## 3. Frontend Setup & Startup

Open a second terminal window:
```bash
cd /Users/bharanikumar.j/Documents/EVChargeOptimization/frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
- Web dashboard accessible at: `http://127.0.0.1:5174`

---

## 4. Running Automated Tests & Demos

### Run Backend Pytest Suite
```bash
cd /Users/bharanikumar.j/Documents/EVChargeOptimization
./.venv/bin/pytest backend/tests
```

### Run End-to-End Feedback Loop Verification
```bash
./.venv/bin/python backend/scripts/run_feedback_loop_demo.py
```

### Run Frontend Type Check & Production Build
```bash
cd /Users/bharanikumar.j/Documents/EVChargeOptimization/frontend
npm run build
```

---

## 5. Using PostgreSQL Locally (Optional)

To connect to a local PostgreSQL instance instead of SQLite:
1. Create a local PostgreSQL database:
   ```bash
   createdb evcharge_opt
   ```
2. Copy `.env.example` to `.env` and set:
   ```env
   DATABASE_URL=postgresql+psycopg://postgres:your_password@127.0.0.1:5432/evcharge_opt
   ```
3. Run migrations:
   ```bash
   cd backend && ../.venv/bin/alembic upgrade head && cd ..
   ./.venv/bin/python backend/scripts/seed_data.py
   ```
