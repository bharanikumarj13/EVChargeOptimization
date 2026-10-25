from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class GridGroup(Base):
    __tablename__ = "grid_groups"

    grid_group_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    grid_group_name: Mapped[str] = mapped_column(String(128), nullable=False)
    grid_limit_kw: Mapped[float] = mapped_column(Float, nullable=False)
    other_load_kw: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    stations = relationship("Station", back_populates="grid_group", cascade="all, delete-orphan")

    @property
    def residual_capacity_kw(self) -> float:
        return max(0.0, self.grid_limit_kw - self.other_load_kw)
