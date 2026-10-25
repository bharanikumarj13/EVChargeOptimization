from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Station(Base):
    __tablename__ = "stations"

    station_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    station_name: Mapped[str] = mapped_column(String(128), nullable=False)
    charger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    available_chargers: Mapped[int] = mapped_column(Integer, nullable=False)
    charger_power_kw_per_charger: Mapped[float] = mapped_column(Float, nullable=False)
    station_power_limit_kw: Mapped[float] = mapped_column(Float, nullable=False)
    avg_session_minutes: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)
    grid_group_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("grid_groups.grid_group_id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    grid_group = relationship("GridGroup", back_populates="stations")
