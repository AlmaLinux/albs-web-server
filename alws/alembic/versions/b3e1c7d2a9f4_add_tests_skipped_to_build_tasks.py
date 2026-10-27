"""Add tests_skipped to build_tasks

Revision ID: b3e1c7d2a9f4
Revises: 9ca5afd67819
Create Date: 2026-10-27 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b3e1c7d2a9f4'
down_revision = '9ca5afd67819'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'build_tasks',
        sa.Column('tests_skipped', sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column('build_tasks', 'tests_skipped')
