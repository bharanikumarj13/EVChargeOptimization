import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse, StationFeedbackOutcome
from app.services.feedback_service import FeedbackService
from app.repositories.feedback_repo import FeedbackRepository
from app.repositories.operational_adjustment_repo import OperationalAdjustmentRepository

router = APIRouter(tags=["Feedback"])


@router.post(
    "/allocations/{allocation_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_allocation_feedback(
    allocation_id: str,
    req: Optional[FeedbackCreateRequest] = None,
    db: Session = Depends(get_db),
):
    service = FeedbackService(db)
    return service.submit_allocation_feedback(allocation_id, req)


@router.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
def get_feedback(feedback_id: str, db: Session = Depends(get_db)):
    repo = FeedbackRepository(db)
    adj_repo = OperationalAdjustmentRepository(db)
    record = repo.get_by_id(feedback_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback record '{feedback_id}' not found.",
        )
    adj = adj_repo.get_by_source_feedback(record.feedback_id)

    outcomes_raw = json.loads(record.station_outcomes_json)
    station_outcomes = [StationFeedbackOutcome(**o) for o in outcomes_raw]

    return FeedbackResponse(
        feedback_id=record.feedback_id,
        scenario_id=record.scenario_id,
        forecast_id=record.forecast_id,
        allocation_id=record.allocation_id,
        outcome_kind=record.outcome_kind,
        interval_start=record.interval_start,
        interval_end=record.interval_end,
        station_outcomes=station_outcomes,
        deferred_fraction=record.deferred_fraction,
        submission_status=record.submission_status,
        idempotency_key=record.idempotency_key,
        retry_count=record.retry_count,
        error_details=record.error_details,
        operational_adjustment_id=adj.operational_adjustment_id if adj else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/feedback", response_model=List[FeedbackResponse])
def list_feedback(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    repo = FeedbackRepository(db)
    adj_repo = OperationalAdjustmentRepository(db)
    records = repo.get_recent(limit=limit)

    results = []
    for record in records:
        adj = adj_repo.get_by_source_feedback(record.feedback_id)
        outcomes_raw = json.loads(record.station_outcomes_json)
        station_outcomes = [StationFeedbackOutcome(**o) for o in outcomes_raw]
        results.append(
            FeedbackResponse(
                feedback_id=record.feedback_id,
                scenario_id=record.scenario_id,
                forecast_id=record.forecast_id,
                allocation_id=record.allocation_id,
                outcome_kind=record.outcome_kind,
                interval_start=record.interval_start,
                interval_end=record.interval_end,
                station_outcomes=station_outcomes,
                deferred_fraction=record.deferred_fraction,
                submission_status=record.submission_status,
                idempotency_key=record.idempotency_key,
                retry_count=record.retry_count,
                error_details=record.error_details,
                operational_adjustment_id=adj.operational_adjustment_id if adj else None,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
    return results
