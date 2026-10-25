from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.grid_group import GridGroupCreate, GridGroupUpdate, GridGroupResponse
from app.repositories.grid_group_repo import GridGroupRepository

router = APIRouter(prefix="/grid-groups", tags=["Grid Groups"])


@router.get("", response_model=List[GridGroupResponse])
def list_grid_groups(db: Session = Depends(get_db)):
    repo = GridGroupRepository(db)
    groups = repo.get_all()
    # Compute residual capacity
    return [
        GridGroupResponse(
            grid_group_id=g.grid_group_id,
            grid_group_name=g.grid_group_name,
            grid_limit_kw=g.grid_limit_kw,
            other_load_kw=g.other_load_kw,
            residual_capacity_kw=g.residual_capacity_kw,
            created_at=g.created_at,
            updated_at=g.updated_at,
        )
        for g in groups
    ]


@router.post("", response_model=GridGroupResponse, status_code=status.HTTP_201_CREATED)
def create_grid_group(group_in: GridGroupCreate, db: Session = Depends(get_db)):
    repo = GridGroupRepository(db)
    existing = repo.get_by_id(group_in.grid_group_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Grid group with ID '{group_in.grid_group_id}' already exists.",
        )
    created = repo.create(group_in)
    return GridGroupResponse(
        grid_group_id=created.grid_group_id,
        grid_group_name=created.grid_group_name,
        grid_limit_kw=created.grid_limit_kw,
        other_load_kw=created.other_load_kw,
        residual_capacity_kw=created.residual_capacity_kw,
        created_at=created.created_at,
        updated_at=created.updated_at,
    )


@router.get("/{grid_group_id}", response_model=GridGroupResponse)
def get_grid_group(grid_group_id: str, db: Session = Depends(get_db)):
    repo = GridGroupRepository(db)
    group = repo.get_by_id(grid_group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grid group '{grid_group_id}' not found.",
        )
    return GridGroupResponse(
        grid_group_id=group.grid_group_id,
        grid_group_name=group.grid_group_name,
        grid_limit_kw=group.grid_limit_kw,
        other_load_kw=group.other_load_kw,
        residual_capacity_kw=group.residual_capacity_kw,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.put("/{grid_group_id}", response_model=GridGroupResponse)
def update_grid_group(
    grid_group_id: str,
    group_in: GridGroupUpdate,
    db: Session = Depends(get_db),
):
    repo = GridGroupRepository(db)
    group = repo.get_by_id(grid_group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grid group '{grid_group_id}' not found.",
        )
    updated = repo.update(group, group_in)
    return GridGroupResponse(
        grid_group_id=updated.grid_group_id,
        grid_group_name=updated.grid_group_name,
        grid_limit_kw=updated.grid_limit_kw,
        other_load_kw=updated.other_load_kw,
        residual_capacity_kw=updated.residual_capacity_kw,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )
