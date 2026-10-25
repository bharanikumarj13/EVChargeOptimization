from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.scenario import Scenario
from app.schemas.scenario import ScenarioCreate


class ScenarioRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, scenario_id: str) -> Optional[Scenario]:
        return self.db.query(Scenario).filter(Scenario.scenario_id == scenario_id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Scenario]:
        return (
            self.db.query(Scenario)
            .order_by(Scenario.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create(self, obj_in: ScenarioCreate) -> Scenario:
        db_obj = Scenario(**obj_in.model_dump())
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
