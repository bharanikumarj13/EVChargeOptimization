from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.exceptions import EVChargeOptException
from app.api.router import api_router
from app.api.v1.health import get_service_health
from app.db.session import get_db

setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Intelligent EV Charging Allocation and Optimization System API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
origins = settings.cors_origins_list
if not origins:
    origins = ["http://127.0.0.1:5174", "http://localhost:5174"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root-level health endpoint
app.add_api_route(
    "/healthz",
    get_service_health,
    methods=["GET"],
    tags=["Health & Diagnostics"],
    summary="Root Service Health Check",
)

# Mount versioned API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(EVChargeOptException)
async def evcharge_opt_exception_handler(request: Request, exc: EVChargeOptException):
    logger.warning("Application exception: %s (status %s)", exc.message, exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "EVCharge-Opt",
        "description": "Intelligent EV Charging Allocation and Optimization System",
        "status": "operational",
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
        "mode": settings.PREDICT_PROVIDER_MODE,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
