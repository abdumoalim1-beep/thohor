"""link recommendations to catalog entities

Revision ID: 5c72a0e913bf
Revises: 8d6a2b91f314
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5c72a0e913bf"
down_revision: Union[str, None] = "8d6a2b91f314"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("page_id", sa.Uuid(), nullable=True))
    op.add_column("recommendations", sa.Column("product_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_recommendations_page_id", "recommendations", "pages", ["page_id"], ["id"])
    op.create_foreign_key("fk_recommendations_product_id", "recommendations", "products", ["product_id"], ["id"])
    op.create_index("ix_recommendations_page_id", "recommendations", ["page_id"])
    op.create_index("ix_recommendations_product_id", "recommendations", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_product_id", table_name="recommendations")
    op.drop_index("ix_recommendations_page_id", table_name="recommendations")
    op.drop_constraint("fk_recommendations_product_id", "recommendations", type_="foreignkey")
    op.drop_constraint("fk_recommendations_page_id", "recommendations", type_="foreignkey")
    op.drop_column("recommendations", "product_id")
    op.drop_column("recommendations", "page_id")
