from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.station import StationCreate, StationUpdate, StationResponse
from app.repositories.station_repo import StationRepository
from app.repositories.grid_group_repo import GridGroupRepository
from app.optimization.constraints import validate_station_config

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get("", response_model=List[StationResponse])
def list_stations(
    active_only: bool = Query(False, description="Filter for active stations only"),
    db: Session = Depends(get_db),
):
    repo = StationRepository(db)
    return repo.get_all(active_only=active_only)


@router.post("", response_model=StationResponse, status_code=status.HTTP_201_CREATED)
def create_station(station_in: StationCreate, db: Session = Depends(get_db)):
    repo = StationRepository(db)
    existing = repo.get_by_id(station_in.station_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Station with ID '{station_in.station_id}' already exists.",
        )

    # Validate referenced grid group
    gg_repo = GridGroupRepository(db)
    grid_group = gg_repo.get_by_id(station_in.grid_group_id)
    if not grid_group:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Referenced grid group '{station_in.grid_group_id}' does not exist.",
        )

    return repo.create(station_in)


@router.get("/{station_id}", response_model=StationResponse)
def get_station(station_id: str, db: Session = Depends(get_db)):
    repo = StationRepository(db)
    station = repo.get_by_id(station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with ID '{station_id}' not found.",
        )
    return station


@router.put("/{station_id}", response_model=StationResponse)
def update_station(
    station_id: str,
    station_in: StationUpdate,
    db: Session = Depends(get_db),
):
    repo = StationRepository(db)
    station = repo.get_by_id(station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with ID '{station_id}' not found.",
        )

    if station_in.grid_group_id:
        gg_repo = GridGroupRepository(db)
        if not gg_repo.get_by_id(station_in.grid_group_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Referenced grid group '{station_in.grid_group_id}' does not exist.",
            )

    effective_count = (
        station_in.charger_count if station_in.charger_count is not None else station.charger_count
    )
    effective_available = (
        station_in.available_chargers if station_in.available_chargers is not None else station.available_chargers
    )
    if effective_available > effective_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"available_chargers ({effective_available}) cannot exceed charger_count ({effective_count}).",
        )

    return repo.update(station, station_in)


@router.post("/{station_id}/deactivate", response_model=StationResponse)
def deactivate_station(station_id: str, db: Session = Depends(get_db)):
    repo = StationRepository(db)
    station = repo.get_by_id(station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with ID '{station_id}' not found.",
        )
    return repo.deactivate(station)
