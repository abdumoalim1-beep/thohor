"""visibility_run_total_operations_planned

Revision ID: a1f3c9d8e7b2
Revises: 89ce23ff8087
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1f3c9d8e7b2'
down_revision: Union[str, None] = '89ce23ff8087'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('visibility_runs', sa.Column('total_operations_planned', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('visibility_runs', 'total_operations_planned', server_default=None)


def downgrade() -> None:
    op.drop_column('visibility_runs', 'total_operations_planned')
