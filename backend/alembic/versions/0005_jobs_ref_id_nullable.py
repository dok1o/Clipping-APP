"""jobs.ref_id nullable (system jobs like ml_train have no target row)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.alter_column("ref_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE jobs SET ref_id = '00000000-0000-0000-0000-000000000000' WHERE ref_id IS NULL")
    with op.batch_alter_table("jobs") as batch:
        batch.alter_column("ref_id", existing_type=sa.Uuid(), nullable=False)
