import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.operational_adjustment import (
    OperationalAdjustmentResponse,
    StationOperationalAdjustmentItem,
)
from app.repositories.operational_adjustment_repo import OperationalAdjustmentRepository

router = APIRouter(prefix="/operational-adjustments", tags=["Operational Adjustments"])


@router.get("/{operational_adjustment_id}", response_model=OperationalAdjustmentResponse)
def get_operational_adjustment(
    operational_adjustment_id: str,
    db: Session = Depends(get_db),
):
    repo = OperationalAdjustmentRepository(db)
    adj = repo.get_by_id(operational_adjustment_id)
    if not adj:
        raise HTTPException(
            status_code=404,
            detail=f"Operational adjustment '{operational_adjustment_id}' not found.",
        )

    adjustments_raw = json.loads(adj.station_adjustments_json)
    assumptions_raw = json.loads(adj.calculation_assumptions_json)

    return OperationalAdjustmentResponse(
        operational_adjustment_id=adj.operational_adjustment_id,
        source_feedback_id=adj.source_feedback_id,
        parent_forecast_id=adj.parent_forecast_id,
        target_interval_start=adj.target_interval_start,
        target_interval_end=adj.target_interval_end,
        station_adjustments=[StationOperationalAdjustmentItem(**item) for item in adjustments_raw],
        calculation_assumptions=assumptions_raw,
        created_at=adj.created_at,
    )


@router.get("", response_model=List[OperationalAdjustmentResponse])
def list_operational_adjustments(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    repo = OperationalAdjustmentRepository(db)
    items = repo.get_all(limit=limit)
    res = []
    for adj in items:
        adjustments_raw = json.loads(adj.station_adjustments_json)
        assumptions_raw = json.loads(adj.calculation_assumptions_json)
        res.append(
            OperationalAdjustmentResponse(
                operational_adjustment_id=adj.operational_adjustment_id,
                source_feedback_id=adj.source_feedback_id,
                parent_forecast_id=adj.parent_forecast_id,
                target_interval_start=adj.target_interval_start,
                target_interval_end=adj.target_interval_end,
                station_adjustments=[StationOperationalAdjustmentItem(**item) for item in adjustments_raw],
                calculation_assumptions=assumptions_raw,
                created_at=adj.created_at,
            )
        )
    return res
