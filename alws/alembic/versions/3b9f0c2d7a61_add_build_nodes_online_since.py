"""Add build_nodes.online_since

Revision ID: 3b9f0c2d7a61
Revises: 5153ee78f247
Create Date: 2026-11-25 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '3b9f0c2d7a61'
down_revision = '5153ee78f247'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'build_nodes',
        sa.Column('online_since', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column('build_nodes', 'online_since')
