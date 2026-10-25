from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class FeedbackRecord(Base):
    __tablename__ = "feedback_records"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    forecast_id: Mapped[str] = mapped_column(String(64), nullable=False)
    allocation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("allocation_runs.allocation_id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    outcome_kind: Mapped[str] = mapped_column(String(32), default="simulation", nullable=False)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    station_outcomes_json: Mapped[str] = mapped_column(Text, nullable=False)
    deferred_fraction: Mapped[float] = mapped_column(Float, default=0.70, nullable=False)
    submission_status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)  # submitted, pending, failed
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_details: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
