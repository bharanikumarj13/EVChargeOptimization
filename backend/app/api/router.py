from fastapi import APIRouter, Depends
from app.core.security import verify_opt_service_token
from app.api.v1 import (
    health,
    stations,
    grid_groups,
    scenarios,
    allocations,
    feedback,
    operational_adjustments,
    reports,
    forecasts,
)

api_router = APIRouter()

# Public diagnostic and operational probes
api_router.include_router(health.router)

# Business, allocation, and partner integration routes protected by dual server/browser authentication
api_router.include_router(stations.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(grid_groups.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(scenarios.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(allocations.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(feedback.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(operational_adjustments.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(reports.router, dependencies=[Depends(verify_opt_service_token)])
api_router.include_router(forecasts.router, dependencies=[Depends(verify_opt_service_token)])
