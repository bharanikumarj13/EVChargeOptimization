import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.allocation import (
    AllocationRunRequest,
    AllocationRunResponse,
    AllocationRunSummary,
    StationAllocationResultSchema,
)
from app.services.allocation_service import AllocationService
from app.repositories.allocation_repo import AllocationRepository
from app.models.allocation import AllocationRun

router = APIRouter(tags=["Allocations"])


@router.post("/allocations/run", response_model=AllocationRunResponse, status_code=status.HTTP_201_CREATED)
def run_allocation(req: AllocationRunRequest, db: Session = Depends(get_db)):
    service = AllocationService(db)
    return service.run_allocation(req)


@router.get("/allocations/{allocation_id}", response_model=AllocationRunResponse)
def get_allocation(allocation_id: str, db: Session = Depends(get_db)):
    repo = AllocationRepository(db)
    alloc = repo.get_by_id(allocation_id)
    if not alloc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation '{allocation_id}' not found.",
        )

    # Format result schemas
    result_schemas = [
        StationAllocationResultSchema(
            station_id=res.station_id,
            predicted_arrivals=res.predicted_arrivals,
            predicted_energy_kwh=res.predicted_energy_kwh,
            estimated_served=res.estimated_served,
            estimated_unserved=res.estimated_unserved,
            allocated_power_kw=res.allocated_power_kw,
            estimated_served_energy_kwh=res.estimated_served_energy_kwh,
            estimated_unserved_energy_kwh=res.estimated_unserved_energy_kwh,
            estimated_wait_minutes=res.estimated_wait_minutes,
            charger_utilization_pct=res.charger_utilization_pct,
            warnings=json.loads(res.warnings_json) if res.warnings_json else [],
        )
        for res in alloc.results
    ]

    return AllocationRunResponse(
        allocation_id=alloc.allocation_id,
        scenario_id=alloc.scenario_id,
        forecast_id=alloc.forecast_id,
        operational_adjustment_id=alloc.operational_adjustment_id,
        interval_start=alloc.interval_start,
        interval_end=alloc.interval_end,
        status=alloc.status,
        outcome_kind=alloc.outcome_kind,
        algorithm_version=alloc.algorithm_version,
        objective_description=alloc.objective_description,
        constraint_validation_passed=alloc.constraint_validation_passed,
        warnings=json.loads(alloc.warnings_json) if alloc.warnings_json else [],
        results=result_schemas,
        created_at=alloc.created_at,
    )


@router.get("/scenarios/{scenario_id}/allocations", response_model=List[AllocationRunSummary])
def list_scenario_allocations(
    scenario_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = AllocationRepository(db)
    runs = repo.get_by_scenario(scenario_id, limit=limit)
    summaries = []
    for r in runs:
        tot_arr = sum(res.predicted_arrivals for res in r.results)
        tot_srv = sum(res.estimated_served for res in r.results)
        tot_uns = sum(res.estimated_unserved for res in r.results)
        tot_pwr = sum(res.allocated_power_kw for res in r.results)
        avg_utl = (
            sum(res.charger_utilization_pct for res in r.results) / len(r.results)
            if r.results else 0.0
        )
        summaries.append(
            AllocationRunSummary(
                allocation_id=r.allocation_id,
                scenario_id=r.scenario_id,
                forecast_id=r.forecast_id,
                operational_adjustment_id=r.operational_adjustment_id,
                interval_start=r.interval_start,
                interval_end=r.interval_end,
                status=r.status,
                outcome_kind=r.outcome_kind,
                constraint_validation_passed=r.constraint_validation_passed,
                total_arrivals=round(tot_arr, 1),
                total_served=round(tot_srv, 1),
                total_unserved=round(tot_uns, 1),
                total_allocated_power_kw=round(tot_pwr, 1),
                avg_utilization_pct=round(avg_utl, 1),
                created_at=r.created_at,
            )
        )
    return summaries


@router.get("/allocations", response_model=List[AllocationRunSummary])
def list_recent_allocations(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    repo = AllocationRepository(db)
    runs = repo.get_recent(limit=limit)
    summaries = []
    for r in runs:
        tot_arr = sum(res.predicted_arrivals for res in r.results)
        tot_srv = sum(res.estimated_served for res in r.results)
        tot_uns = sum(res.estimated_unserved for res in r.results)
        tot_pwr = sum(res.allocated_power_kw for res in r.results)
        avg_utl = (
            sum(res.charger_utilization_pct for res in r.results) / len(r.results)
            if r.results else 0.0
        )
        summaries.append(
            AllocationRunSummary(
                allocation_id=r.allocation_id,
                scenario_id=r.scenario_id,
                forecast_id=r.forecast_id,
                operational_adjustment_id=r.operational_adjustment_id,
                interval_start=r.interval_start,
                interval_end=r.interval_end,
                status=r.status,
                outcome_kind=r.outcome_kind,
                constraint_validation_passed=r.constraint_validation_passed,
                total_arrivals=round(tot_arr, 1),
                total_served=round(tot_srv, 1),
                total_unserved=round(tot_uns, 1),
                total_allocated_power_kw=round(tot_pwr, 1),
                avg_utilization_pct=round(avg_utl, 1),
                created_at=r.created_at,
            )
        )
    return summaries
