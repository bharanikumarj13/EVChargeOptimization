import uuid
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.forecast import ForecastResponse, ForecastCreateRequest, ForecastAcknowledgement
from app.integrations import get_forecast_provider
from app.repositories.forecast_snapshot_repo import ForecastSnapshotRepository
from app.core.exceptions import (
    EntityNotFoundError,
    InvalidForecastError,
    ProviderIntegrationError,
    StationMappingError,
)

router = APIRouter(prefix="/forecasts", tags=["Forecasts"])


@router.post("", response_model=ForecastAcknowledgement, status_code=status.HTTP_201_CREATED)
def create_baseline_forecast(
    req: ForecastCreateRequest,
    db: Session = Depends(get_db),
):
    provider = get_forecast_provider()
    try:
        ack = provider.create_forecast(req)
        # Fetch and persist immutable baseline snapshot
        forecast_data = provider.get_forecast(ack.forecast_id, scenario_id=req.scenario_id)
        snapshot_repo = ForecastSnapshotRepository(db)
        existing = snapshot_repo.get_by_forecast_id(ack.forecast_id)
        if not existing and forecast_data.intervals:
            snapshot_repo.save_snapshot(
                snapshot_id=f"SNAP-{uuid.uuid4().hex[:8].upper()}",
                items=forecast_data.intervals,
            )
        return ack
    except (InvalidForecastError, ValueError, StationMappingError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ProviderIntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message)


@router.get("/{forecast_id}", response_model=ForecastResponse)
def get_forecast(
    forecast_id: str,
    scenario_id: Optional[str] = Query(None),
):
    provider = get_forecast_provider()
    try:
        return provider.get_forecast(forecast_id, scenario_id=scenario_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except (InvalidForecastError, StationMappingError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    except ProviderIntegrationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=e.message)
