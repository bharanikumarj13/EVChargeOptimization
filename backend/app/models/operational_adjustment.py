from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class OperationalAdjustment(Base):
    __tablename__ = "operational_adjustments"

    operational_adjustment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_feedback_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("feedback_records.feedback_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_forecast_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    station_adjustments_json: Mapped[str] = mapped_column(Text, nullable=False)
    deferred_demand_contribution_json: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_assumptions_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
