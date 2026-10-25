from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.grid_group import GridGroup
from app.schemas.grid_group import GridGroupCreate, GridGroupUpdate


class GridGroupRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, grid_group_id: str) -> Optional[GridGroup]:
        return self.db.query(GridGroup).filter(GridGroup.grid_group_id == grid_group_id).first()

    def get_all(self) -> List[GridGroup]:
        return self.db.query(GridGroup).order_by(GridGroup.grid_group_id).all()

    def create(self, obj_in: GridGroupCreate) -> GridGroup:
        db_obj = GridGroup(**obj_in.model_dump())
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def update(self, db_obj: GridGroup, obj_in: GridGroupUpdate) -> GridGroup:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
