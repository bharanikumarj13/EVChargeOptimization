from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.operational_adjustment import OperationalAdjustment


class OperationalAdjustmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, operational_adjustment_id: str) -> Optional[OperationalAdjustment]:
        return (
            self.db.query(OperationalAdjustment)
            .filter(OperationalAdjustment.operational_adjustment_id == operational_adjustment_id)
            .first()
        )

    def get_by_source_feedback(self, source_feedback_id: str) -> Optional[OperationalAdjustment]:
        return (
            self.db.query(OperationalAdjustment)
            .filter(OperationalAdjustment.source_feedback_id == source_feedback_id)
            .first()
        )

    def get_all(self, limit: int = 50) -> List[OperationalAdjustment]:
        return (
            self.db.query(OperationalAdjustment)
            .order_by(OperationalAdjustment.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(self, data: dict) -> OperationalAdjustment:
        obj = OperationalAdjustment(**data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
