"""Remove automatically seeded categories.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    categories = sa.table(
        "categories",
        sa.column("name", sa.String()),
        sa.column("sort_order", sa.Integer()),
    )
    op.execute(
        sa.delete(categories).where(
            sa.or_(
                sa.and_(categories.c.name == "داستان", categories.c.sort_order == 0),
                sa.and_(categories.c.name == "هنر و طراحی", categories.c.sort_order == 1),
                sa.and_(categories.c.name == "تاریخ", categories.c.sort_order == 2),
                sa.and_(categories.c.name == "علمی", categories.c.sort_order == 3),
            )
        )
    )


def downgrade() -> None:
    # Removed seed data is intentionally not recreated on rollback.
    pass
