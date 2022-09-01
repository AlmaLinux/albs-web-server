"""Removed Distributions

Revision ID: 26b384d34941
Revises: 26b384d3493f
Create Date: 2022-09-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "26b384d34941"
down_revision = "26b384d3493f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE builds SET released = false WHERE released is NULL"))


def downgrade():
    pass
