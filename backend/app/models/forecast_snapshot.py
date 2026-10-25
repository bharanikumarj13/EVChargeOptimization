from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    forecast_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=True)
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    predicted_arrivals: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), default="v1.0", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
