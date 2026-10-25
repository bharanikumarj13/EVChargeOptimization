from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.feedback import FeedbackRecord


class FeedbackRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, feedback_id: str) -> Optional[FeedbackRecord]:
        return self.db.query(FeedbackRecord).filter(FeedbackRecord.feedback_id == feedback_id).first()

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[FeedbackRecord]:
        return (
            self.db.query(FeedbackRecord)
            .filter(FeedbackRecord.idempotency_key == idempotency_key)
            .first()
        )

    def get_by_allocation_id(self, allocation_id: str) -> Optional[FeedbackRecord]:
        return (
            self.db.query(FeedbackRecord)
            .filter(FeedbackRecord.allocation_id == allocation_id)
            .first()
        )

    def get_recent(self, limit: int = 50) -> List[FeedbackRecord]:
        return (
            self.db.query(FeedbackRecord)
            .order_by(FeedbackRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def create(self, record_data: dict) -> FeedbackRecord:
        record = FeedbackRecord(**record_data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_status(
        self,
        record: FeedbackRecord,
        status: str,
        retry_count: Optional[int] = None,
        error_details: Optional[str] = None,
    ) -> FeedbackRecord:
        record.submission_status = status
        if retry_count is not None:
            record.retry_count = retry_count
        record.error_details = error_details
        self.db.commit()
        self.db.refresh(record)
        return record
