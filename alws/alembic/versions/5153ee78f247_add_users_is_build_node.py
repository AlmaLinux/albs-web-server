"""Add users.is_build_node and users.build_node_name

Revision ID: 5153ee78f247
Revises: c71224bebd19
Create Date: 2026-11-20 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '5153ee78f247'
down_revision = 'c71224bebd19'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column(
            'is_build_node',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'users',
        sa.Column('build_node_name', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('users', 'build_node_name')
    op.drop_column('users', 'is_build_node')
