"""product_rating_sku_last_seen_fields

Revision ID: 45fdedc04810
Revises: 2b7104c6db30
Create Date: 2026-08-17 03:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '45fdedc04810'
down_revision: Union[str, None] = '2b7104c6db30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: autogenerate again picked up the same unrelated pre-existing drift
# on analysis_component_snapshots as 989b5eb23ad0/2b7104c6db30 — stripped.
# Only the new `products` columns for Phase 3 (crawl reordering / catalog
# data richness) are included here.


def upgrade() -> None:
    op.add_column('products', sa.Column('original_price', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('sku', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('products', sa.Column('rating', sa.Float(), nullable=True))
    op.add_column('products', sa.Column('review_count', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('last_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')))


def downgrade() -> None:
    op.drop_column('products', 'last_seen_at')
    op.drop_column('products', 'review_count')
    op.drop_column('products', 'rating')
    op.drop_column('products', 'sku')
    op.drop_column('products', 'original_price')
