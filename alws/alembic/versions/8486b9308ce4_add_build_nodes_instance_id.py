"""Add build_nodes.instance_id and build_nodes.instance_changed_at

Revision ID: 8486b9308ce4
Revises: 0da51b7c6303
Create Date: 2026-11-18 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '8486b9308ce4'
down_revision = '0da51b7c6303'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'build_nodes',
        sa.Column('instance_id', sa.Text(), nullable=True),
    )
    op.add_column(
        'build_nodes',
        sa.Column('instance_changed_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column('build_nodes', 'instance_changed_at')
    op.drop_column('build_nodes', 'instance_id')
