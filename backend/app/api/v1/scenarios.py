import json
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.scenario import ScenarioCreate, ScenarioResponse
from app.repositories.scenario_repo import ScenarioRepository
from app.models.allocation import AllocationRun
from app.models.feedback import FeedbackRecord
from app.models.operational_adjustment import OperationalAdjustment

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


@router.get("", response_model=List[ScenarioResponse])
def list_scenarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    repo = ScenarioRepository(db)
    scenarios = repo.get_all(skip=skip, limit=limit)
    res = []
    for s in scenarios:
        count = db.query(AllocationRun).filter(AllocationRun.scenario_id == s.scenario_id).count()
        item = ScenarioResponse.model_validate(s)
        item.allocation_count = count
        res.append(item)
    return res


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(scenario_in: ScenarioCreate, db: Session = Depends(get_db)):
    repo = ScenarioRepository(db)
    existing = repo.get_by_id(scenario_in.scenario_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Scenario with ID '{scenario_in.scenario_id}' already exists.",
        )
    created = repo.create(scenario_in)
    res = ScenarioResponse.model_validate(created)
    res.allocation_count = 0
    return res


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    repo = ScenarioRepository(db)
    scenario = repo.get_by_id(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found.",
        )
    count = db.query(AllocationRun).filter(AllocationRun.scenario_id == scenario.scenario_id).count()
    res = ScenarioResponse.model_validate(scenario)
    res.allocation_count = count
    return res


@router.get("/{scenario_id}/iterations")
def get_scenario_iterations(scenario_id: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Returns full chronological trace of iterations, allocations, feedback,
    and operational adjustments for this scenario.
    """
    repo = ScenarioRepository(db)
    scenario = repo.get_by_id(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found.",
        )

    allocations = (
        db.query(AllocationRun)
        .filter(AllocationRun.scenario_id == scenario_id)
        .order_by(AllocationRun.created_at.asc())
        .all()
    )

    iterations_trace = []
    for idx, alloc in enumerate(allocations, 1):
        # Find feedback for this allocation
        feedback = db.query(FeedbackRecord).filter(FeedbackRecord.allocation_id == alloc.allocation_id).first()
        adjustment = None
        if feedback:
            adjustment = (
                db.query(OperationalAdjustment)
                .filter(OperationalAdjustment.source_feedback_id == feedback.feedback_id)
                .first()
            )

        iterations_trace.append({
            "iteration_index": idx,
            "allocation_id": alloc.allocation_id,
            "forecast_id": alloc.forecast_id,
            "operational_adjustment_id": alloc.operational_adjustment_id,
            "is_feedback_adjusted": alloc.operational_adjustment_id is not None,
            "interval_start": alloc.interval_start.isoformat(),
            "interval_end": alloc.interval_end.isoformat(),
            "status": alloc.status,
            "outcome_kind": alloc.outcome_kind,
            "constraint_validation_passed": alloc.constraint_validation_passed,
            "feedback": {
                "feedback_id": feedback.feedback_id,
                "submission_status": feedback.submission_status,
                "deferred_fraction": feedback.deferred_fraction,
                "created_at": feedback.created_at.isoformat(),
            } if feedback else None,
            "next_adjustment": {
                "operational_adjustment_id": adjustment.operational_adjustment_id,
                "target_interval_start": adjustment.target_interval_start.isoformat(),
                "target_interval_end": adjustment.target_interval_end.isoformat(),
                "station_adjustments": json.loads(adjustment.station_adjustments_json),
            } if adjustment else None,
            "created_at": alloc.created_at.isoformat(),
        })

    return iterations_trace
