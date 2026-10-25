# Render Cloud Deployment Guide

This guide details how to prepare, configure, and deploy **EVCharge-Opt** to [Render](https://render.com).

> [!IMPORTANT]
> **Safety Notice:** Do not trigger deployment commands until explicit approval is granted. Follow these instructions when you are ready to authorize the cloud deployment.

---

## 1. Cloud Architecture & Topology

The target production deployment topology on Render comprises:

1. **Database:** Render Managed PostgreSQL (Free / Standard Tier).
2. **Backend:** Render Web Service running the FastAPI application (Python 3.12).
3. **Frontend:** Render Static Site serving the compiled React / TypeScript SPA.
4. **Partner Service:** Independent EVCharge-Predict service communicating over secure HTTPS.

```
[ User Browser ]
       │
       ▼ (HTTPS)
┌───────────────────────────────────────┐
│ Render Static Site                    │
│ URL: https://evcharge-opt.onrender.com │
│ (React 18 SPA from dist/)             │
└──────────────────┬────────────────────┘
                   │
                   ▼ (HTTPS REST / CORS)
┌───────────────────────────────────────┐
│ Render Web Service                    │
│ URL: https://evcharge-opt-api.onrender.com
│ (FastAPI, Uvicorn, port: $PORT)       │
└─────────┬───────────────────┬─────────┘
          │                   │
          ▼                   ▼ (HTTPS Service Auth)
┌───────────────────┐   ┌─────────────────────────────┐
│ Render Managed DB │   │ EVCharge-Predict Partner    │
│ PostgreSQL        │   │ (External Web Service)      │
└───────────────────┘   └─────────────────────────────┘
```

---

## 2. Option A: One-Click Render Blueprint Deployment (Recommended)

The repository provides an automated [render.yaml](../render.yaml) Blueprint that sets up the database, backend web service, and frontend static site with correct environment variables and wiring in one operation:

1. Connect your GitHub repository to Render.
2. In the Render Dashboard, click **Blueprints** → **New Blueprint Instance**.
3. Select your `EVChargeOptimization` repository.
4. Render will detect `render.yaml` and prompt you to create:
   - `evcharge-opt-db` (PostgreSQL Database)
   - `evcharge-opt-api` (FastAPI Web Service)
   - `evcharge-opt` (React Static Site)
5. Click **Apply**. Render will automatically provision the managed database, build the frontend, run database migrations, seed baseline data, and start the services.

---

## 3. Option B: Manual Dashboard Configuration

If configuring services manually via the Render UI:

### Step 1: Create Render PostgreSQL Database
1. In the Render Dashboard, click **New +** → **PostgreSQL**.
2. Settings:
   - **Name:** `evcharge-opt-db`
   - **Database:** `evcharge_opt`
   - **User:** `evcharge_user`
   - **Region:** Frankfurt (EU) or Oregon (US)
3. Copy the **Internal Database URL** (e.g. `postgres://evcharge_user:...@dpg-...:5432/evcharge_opt`).
   *(Note: The EVCharge-Opt database engine automatically converts `postgres://` to `postgresql+psycopg://` at runtime).*

---

### Step 2: Deploy Backend Web Service

1. Click **New +** → **Web Service**.
2. Connect your repository.
3. Configure settings:
   - **Name:** `evcharge-opt-api`
   - **Region:** (Same region as your database)
   - **Branch:** `main`
   - **Root Directory:** *(leave blank or set to repository root)*
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     pip install --upgrade pip && pip install -r backend/requirements.txt
     ```
   - **Start Command:**
     ```bash
     bash backend/scripts/start_production.sh
     ```
   - **Health Check Path:** `/healthz`

4. Environment Variables:
   | Key | Value | Description |
   | :--- | :--- | :--- |
   | `PYTHON_VERSION` | `3.12.7` | Explicit Python 3.12 runtime |
   | `APP_ENV` | `production` | Production environment flag |
   | `DATABASE_URL` | *(Paste Internal Database URL from Step 1)* | Managed PostgreSQL connection |
   | `PREDICT_PROVIDER_MODE` | `mock` | Forecast mode (keep mock until live partner verified) |
   | `PREDICT_API_BASE_URL` | `http://127.0.0.1:8001` | Placeholder partner URL (unverified until partner confirms) |
   | `CORS_ORIGINS` | `https://evcharge-opt.onrender.com,http://127.0.0.1:5174,http://localhost:5174` | Allowed frontend origins |
   | `LOG_LEVEL` | `INFO` | Logging level |
   | `STATION_INTEGRATION_PROFILE` | `five_station_mock` | Active station profile |
   | `CONFIRM_PHYSICAL_STATION_MAPPINGS` | `false` | Physical verification guard |
   | `PREDICT_SUPPORTED_STATIONS` | `ST-001,ST-002,ST-003` | Supported canonical predictor stations |

---

### Step 3: Deploy Frontend Static Site

1. Click **New +** → **Static Site**.
2. Connect your repository.
3. Configure settings:
   - **Name:** `evcharge-opt`
   - **Branch:** `main`
   - **Root Directory:** `frontend`
   - **Build Command:**
     ```bash
     npm ci && npm run build
     ```
   - **Publish Directory:** `dist`

4. Environment Variables:
   | Key | Value | Description |
   | :--- | :--- | :--- |
   | `VITE_API_BASE_URL` | `https://evcharge-opt-api.onrender.com` | Public URL of the FastAPI Backend |

5. Configure Rewrite Rules for React Router:
   - Go to **Redirects/Rewrites** tab:
   - **Source:** `/*`
   - **Destination:** `/index.html`
   - **Action:** `Rewrite`

---

## 5. Post-Deployment Verification (Smoke Test)

1. Verify backend health endpoint:
   ```bash
   curl -s https://evcharge-opt-api.onrender.com/healthz
   # Expected: {"status":"ok","service":"EVCharge-Opt",...}
   ```
2. Verify integration telemetry:
   ```bash
   curl -s https://evcharge-opt-api.onrender.com/api/v1/integration/health
   # Expected: {"status":"healthy","provider_mode":"mock",...}
   ```
3. Open `https://evcharge-opt.onrender.com` in your browser:
   - Navigate to **Overview**: Verify station metrics and charts load.
   - Navigate to **Run Optimization**: Run an allocation on Interval #1.
   - Click **Submit Feedback**: Verify feedback record is persisted and creates an operational adjustment.
   - Navigate to **History & Reports**: Click **Export Allocations CSV** and verify spreadsheet download.
