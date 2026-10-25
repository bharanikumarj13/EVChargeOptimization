"""Add payload_hash and unique constraint on allocation_id in feedback_records

Revision ID: 002_feedback_idempotency_and_fingerprint
Revises: 001_initial_schema
Create Date: 2026-10-25 22:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_feedback_idempotency_and_fingerprint"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("feedback_records") as batch_op:
        batch_op.add_column(sa.Column("payload_hash", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_feedback_records_allocation_id", ["allocation_id"])


def downgrade() -> None:
    with op.batch_alter_table("feedback_records") as batch_op:
        batch_op.drop_constraint("uq_feedback_records_allocation_id", type_="unique")
        batch_op.drop_column("payload_hash")
