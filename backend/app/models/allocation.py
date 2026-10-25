from datetime import datetime, timezone
from typing import List
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class AllocationRun(Base):
    __tablename__ = "allocation_runs"

    allocation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("scenarios.scenario_id", ondelete="CASCADE"),
        nullable=False,
    )
    forecast_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operational_adjustment_id: Mapped[str] = mapped_column(String(64), nullable=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)  # success, infeasible, failed
    outcome_kind: Mapped[str] = mapped_column(String(32), default="simulation", nullable=False)  # simulation, observed
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1.0-priority-heuristic", nullable=False)
    objective_description: Mapped[str] = mapped_column(Text, nullable=False)
    constraint_validation_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    scenario = relationship("Scenario", back_populates="allocations")
    results = relationship("AllocationResult", back_populates="allocation", cascade="all, delete-orphan")


class AllocationResult(Base):
    __tablename__ = "allocation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    allocation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("allocation_runs.allocation_id", ondelete="CASCADE"),
        nullable=False,
    )
    station_id: Mapped[str] = mapped_column(String(64), nullable=False)
    predicted_arrivals: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_served: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_unserved: Mapped[float] = mapped_column(Float, nullable=False)
    allocated_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_served_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_unserved_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_wait_minutes: Mapped[float] = mapped_column(Float, nullable=True)
    charger_utilization_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    allocation = relationship("AllocationRun", back_populates="results")
