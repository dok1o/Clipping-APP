"""jobs.type check constraint: 'train' -> 'ml_train' (Stage 7)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "'transcribe', 'render', 'text_gen', 'publish', 'metrics_sync', 'train'"
_NEW = "'transcribe', 'render', 'text_gen', 'publish', 'metrics_sync', 'ml_train'"


def upgrade() -> None:
    op.execute("UPDATE jobs SET type = 'ml_train' WHERE type = 'train'")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("type", type_="check")
        batch.create_check_constraint("type", f"type IN ({_NEW})")


def downgrade() -> None:
    op.execute("UPDATE jobs SET type = 'train' WHERE type = 'ml_train'")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("type", type_="check")
        batch.create_check_constraint("type", f"type IN ({_OLD})")
