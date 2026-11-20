"""Add build_tasks.claimed_by_instance

Revision ID: c71224bebd19
Revises: 47350a16723c
Create Date: 2026-11-19 13:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c71224bebd19'
down_revision = '47350a16723c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'build_tasks',
        sa.Column('claimed_by_instance', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('build_tasks', 'claimed_by_instance')
