from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    selected_forecast_id: Mapped[str] = mapped_column(String(64), nullable=False)
    planning_horizon_intervals: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(32), default="mock", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    allocations = relationship("AllocationRun", back_populates="scenario", cascade="all, delete-orphan")
