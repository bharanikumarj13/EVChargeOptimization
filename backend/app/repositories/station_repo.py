from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.station import Station
from app.schemas.station import StationCreate, StationUpdate


class StationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, station_id: str) -> Optional[Station]:
        return self.db.query(Station).filter(Station.station_id == station_id).first()

    def get_all(self, active_only: bool = False) -> List[Station]:
        query = self.db.query(Station)
        if active_only:
            query = query.filter(Station.is_active == True)
        return query.order_by(Station.station_id).all()

    def create(self, obj_in: StationCreate) -> Station:
        db_obj = Station(**obj_in.model_dump())
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def update(self, db_obj: Station, obj_in: StationUpdate) -> Station:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def deactivate(self, db_obj: Station) -> Station:
        db_obj.is_active = False
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
