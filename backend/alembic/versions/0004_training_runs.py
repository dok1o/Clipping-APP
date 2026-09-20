"""training_runs table (Stage 7)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "training_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("val_spearman", sa.Float(), nullable=True),
        sa.Column("baseline_spearman", sa.Float(), nullable=True),
        sa.Column("gate_passed", sa.Boolean(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("model_path", sa.String(512), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("details", _json(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_training_runs"),
    )
    op.create_index("ix_training_runs_created", "training_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_training_runs_created", table_name="training_runs")
    op.drop_table("training_runs")
