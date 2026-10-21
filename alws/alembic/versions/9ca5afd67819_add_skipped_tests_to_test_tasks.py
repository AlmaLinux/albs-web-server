"""Add skipped_tests to test_tasks

Revision ID: 9ca5afd67819
Revises: e9bb2a44defb
Create Date: 2026-10-20 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '9ca5afd67819'
down_revision = 'e9bb2a44defb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'test_tasks',
        sa.Column(
            'skipped_tests',
            sa.ARRAY(sa.TEXT(), dimensions=1),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column('test_tasks', 'skipped_tests')
