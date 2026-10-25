from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.core.config import settings
from app.integrations import get_forecast_provider
from app.schemas.health import HealthResponse, IntegrationHealthResponse

router = APIRouter(tags=["Health & Diagnostics"])


@router.get("/healthz", response_model=HealthResponse)
def get_service_health(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc.__class__.__name__}"

    return HealthResponse(
        status="ok" if "unhealthy" not in db_status else "degraded",
        service="EVCharge-Opt",
        version="0.1.0",
        database=db_status,
        environment=settings.APP_ENV,
    )


@router.get("/integration/health", response_model=IntegrationHealthResponse)
def get_integration_health():
    provider = get_forecast_provider()
    p_health = provider.check_health()

    return IntegrationHealthResponse(
        status=p_health.get("status", "unknown"),
        provider_mode=settings.PREDICT_PROVIDER_MODE,
        is_mock=settings.is_mock_provider,
        configured_api_base_url=settings.get_safe_predict_url(),
        last_successful_request=p_health.get("last_successful_request"),
        feedback_delivery_status="ready",
        recent_errors=[],
        service_version="0.1.0",
        environment=settings.APP_ENV,
    )
