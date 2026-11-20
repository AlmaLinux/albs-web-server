"""Add build_tasks.dispatch_count and build_tasks.dispatch_nodes

Revision ID: 47350a16723c
Revises: 8486b9308ce4
Create Date: 2026-11-19 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '47350a16723c'
down_revision = '8486b9308ce4'
branch_labels = None
depends_on = None


def upgrade():
    # A constant default doesn't rewrite the table
    op.add_column(
        'build_tasks',
        sa.Column(
            'dispatch_count',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.add_column(
        'build_tasks',
        sa.Column(
            'dispatch_nodes',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column('build_tasks', 'dispatch_nodes')
    op.drop_column('build_tasks', 'dispatch_count')
