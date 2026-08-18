"""store_identity_catalog_competitor_tracking_fields

Revision ID: 2b7104c6db30
Revises: 989b5eb23ad0
Create Date: 2026-08-17 02:25:37.306265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '2b7104c6db30'
down_revision: Union[str, None] = '989b5eb23ad0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: autogenerate also picked up unrelated pre-existing drift on
# analysis_component_snapshots (timestamp tz-awareness, JSON vs JSONB) —
# stripped from this migration, same as 989b5eb23ad0's precedent. Only the
# new `stores` columns for Phase 1/2 identity decoupling are included here.


def upgrade() -> None:
    op.add_column('stores', sa.Column('identity_source', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('stores', sa.Column('identity_confidence', sa.Float(), nullable=True))
    op.add_column('stores', sa.Column('last_identity_scan_at', sa.DateTime(), nullable=True))
    op.add_column('stores', sa.Column('catalog_status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='pending'))
    op.add_column('stores', sa.Column('catalog_pages_crawled', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stores', sa.Column('catalog_products_found', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stores', sa.Column('last_catalog_scan_at', sa.DateTime(), nullable=True))
    op.add_column('stores', sa.Column('competitor_discovery_status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='pending'))
    op.add_column('stores', sa.Column('last_competitor_scan_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('stores', 'last_competitor_scan_at')
    op.drop_column('stores', 'competitor_discovery_status')
    op.drop_column('stores', 'last_catalog_scan_at')
    op.drop_column('stores', 'catalog_products_found')
    op.drop_column('stores', 'catalog_pages_crawled')
    op.drop_column('stores', 'catalog_status')
    op.drop_column('stores', 'last_identity_scan_at')
    op.drop_column('stores', 'identity_confidence')
    op.drop_column('stores', 'identity_source')
