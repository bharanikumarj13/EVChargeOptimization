# Windows PowerShell Setup & Development Guide

This guide describes how to run and test **EVCharge-Opt** locally on Windows using PowerShell.

---

## 1. Prerequisites Check

Open PowerShell and verify your environment:
```powershell
python --version   # Python 3.12.x
node --version     # v22.x
npm --version      # 10.x
```

---

## 2. Backend Setup & Startup

Navigate to the project root directory:
```powershell
cd C:\path\to\EVChargeOptimization
```

### 2.1 Virtual Environment
```powershell
# Set execution policy for the current terminal session if script execution is disabled
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Create local virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install pinned backend dependencies
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

### 2.2 Database Initialization & Migrations
```powershell
# Apply schema migrations via Alembic
cd backend
..\.venv\Scripts\alembic.exe upgrade head
cd ..

# Seed baseline stations and grid groups
.\.venv\Scripts\python.exe backend\scripts\seed_data.py
```

### 2.3 Start FastAPI Backend
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --host 127.0.0.1 --port 8002 --reload
```
- API is running at: `http://127.0.0.1:8002`
- Interactive Swagger documentation: `http://127.0.0.1:8002/docs`
- Health check: `http://127.0.0.1:8002/healthz`

---

## 3. Frontend Setup & Startup

Open a second PowerShell window:
```powershell
cd C:\path\to\EVChargeOptimization\frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
- Web dashboard accessible at: `http://127.0.0.1:5174`

---

## 4. Running Automated Tests on Windows

### Run Pytest Suite
```powershell
cd C:\path\to\EVChargeOptimization
.\.venv\Scripts\pytest.exe backend\tests
```

### Run Feedback Loop Verification Demo
```powershell
.\.venv\Scripts\python.exe backend\scripts\run_feedback_loop_demo.py
```

### Run Frontend Type Check & Production Build
```powershell
cd C:\path\to\EVChargeOptimization\frontend
npm run build
```
