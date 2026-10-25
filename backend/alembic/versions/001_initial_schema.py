"""Initial database schema for EVCharge-Opt

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-25 19:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Grid Groups
    op.create_table(
        "grid_groups",
        sa.Column("grid_group_id", sa.String(length=64), primary_key=True),
        sa.Column("grid_group_name", sa.String(length=128), nullable=False),
        sa.Column("grid_limit_kw", sa.Float(), nullable=False),
        sa.Column("other_load_kw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Stations
    op.create_table(
        "stations",
        sa.Column("station_id", sa.String(length=64), primary_key=True),
        sa.Column("station_name", sa.String(length=128), nullable=False),
        sa.Column("charger_count", sa.Integer(), nullable=False),
        sa.Column("available_chargers", sa.Integer(), nullable=False),
        sa.Column("charger_power_kw_per_charger", sa.Float(), nullable=False),
        sa.Column("station_power_limit_kw", sa.Float(), nullable=False),
        sa.Column("avg_session_minutes", sa.Float(), nullable=False, server_default="45.0"),
        sa.Column("grid_group_id", sa.String(length=64), sa.ForeignKey("grid_groups.grid_group_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. Scenarios
    op.create_table(
        "scenarios",
        sa.Column("scenario_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selected_forecast_id", sa.String(length=64), nullable=False),
        sa.Column("planning_horizon_intervals", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("provider_mode", sa.String(length=32), nullable=False, server_default="mock"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 4. Forecast Snapshots
    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("forecast_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=True),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("predicted_arrivals", sa.Float(), nullable=False),
        sa.Column("predicted_energy_kwh", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False, server_default="v1.0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_snapshots_snapshot_id", "forecast_snapshots", ["snapshot_id"])
    op.create_index("ix_forecast_snapshots_forecast_id", "forecast_snapshots", ["forecast_id"])

    # 5. Allocation Runs
    op.create_table(
        "allocation_runs",
        sa.Column("allocation_id", sa.String(length=64), primary_key=True),
        sa.Column("scenario_id", sa.String(length=64), sa.ForeignKey("scenarios.scenario_id", ondelete="CASCADE"), nullable=False),
        sa.Column("forecast_id", sa.String(length=64), nullable=False),
        sa.Column("operational_adjustment_id", sa.String(length=64), nullable=True),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("outcome_kind", sa.String(length=32), nullable=False, server_default="simulation"),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False, server_default="v1.0-priority-heuristic"),
        sa.Column("objective_description", sa.Text(), nullable=False),
        sa.Column("constraint_validation_passed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 6. Allocation Results
    op.create_table(
        "allocation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("allocation_id", sa.String(length=64), sa.ForeignKey("allocation_runs.allocation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("predicted_arrivals", sa.Float(), nullable=False),
        sa.Column("predicted_energy_kwh", sa.Float(), nullable=False),
        sa.Column("estimated_served", sa.Float(), nullable=False),
        sa.Column("estimated_unserved", sa.Float(), nullable=False),
        sa.Column("allocated_power_kw", sa.Float(), nullable=False),
        sa.Column("estimated_served_energy_kwh", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("estimated_unserved_energy_kwh", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("estimated_wait_minutes", sa.Float(), nullable=True),
        sa.Column("charger_utilization_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 7. Feedback Records
    op.create_table(
        "feedback_records",
        sa.Column("feedback_id", sa.String(length=64), primary_key=True),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("forecast_id", sa.String(length=64), nullable=False),
        sa.Column("allocation_id", sa.String(length=64), sa.ForeignKey("allocation_runs.allocation_id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome_kind", sa.String(length=32), nullable=False, server_default="simulation"),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_outcomes_json", sa.Text(), nullable=False),
        sa.Column("deferred_fraction", sa.Float(), nullable=False, server_default="0.70"),
        sa.Column("submission_status", sa.String(length=32), nullable=False, server_default="submitted"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_records_idempotency_key", "feedback_records", ["idempotency_key"], unique=True)

    # 8. Operational Adjustments
    op.create_table(
        "operational_adjustments",
        sa.Column("operational_adjustment_id", sa.String(length=64), primary_key=True),
        sa.Column("source_feedback_id", sa.String(length=64), sa.ForeignKey("feedback_records.feedback_id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_forecast_id", sa.String(length=64), nullable=False),
        sa.Column("target_interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_adjustments_json", sa.Text(), nullable=False),
        sa.Column("deferred_demand_contribution_json", sa.Text(), nullable=False),
        sa.Column("calculation_assumptions_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 9. Audit Events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("operational_adjustments")
    op.drop_table("feedback_records")
    op.drop_table("allocation_results")
    op.drop_table("allocation_runs")
    op.drop_table("forecast_snapshots")
    op.drop_table("scenarios")
    op.drop_table("stations")
    op.drop_table("grid_groups")
