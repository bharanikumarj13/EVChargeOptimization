from fastapi import APIRouter
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

api_router.include_router(health.router)
api_router.include_router(stations.router)
api_router.include_router(grid_groups.router)
api_router.include_router(scenarios.router)
api_router.include_router(allocations.router)
api_router.include_router(feedback.router)
api_router.include_router(operational_adjustments.router)
api_router.include_router(reports.router)
api_router.include_router(forecasts.router)
