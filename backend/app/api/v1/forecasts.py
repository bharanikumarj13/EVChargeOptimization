from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from app.schemas.forecast import ForecastResponse
from app.integrations import get_forecast_provider
from app.core.exceptions import EntityNotFoundError, InvalidForecastError

router = APIRouter(prefix="/forecasts", tags=["Forecasts"])


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
    except InvalidForecastError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
