"""Add build nodes registry and bind build tasks to nodes

Revision ID: 0da51b7c6303
Revises: 9ca5afd67819
Create Date: 2026-11-18 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0da51b7c6303'
down_revision = '9ca5afd67819'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'build_nodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column(
            'enabled',
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            'drain',
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            'maintenance',
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column('version', sa.Text(), nullable=True),
        sa.Column(
            'supported_arches',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('node_type', sa.Text(), nullable=True),
        sa.Column(
            'pesign_support',
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            'capacity',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('capacity_override', sa.Integer(), nullable=True),
        sa.Column(
            'excluded_packages',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'resources',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column('resources_updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.add_column(
        'build_tasks',
        sa.Column('build_node_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'build_tasks',
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'build_tasks',
        sa.Column('node_reported_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'build_tasks',
        sa.Column('queued_at', sa.DateTime(), nullable=True),
    )
    # build_tasks is big and the build nodes write to it all the time, so
    # nothing is scanned while the table is locked: the foreign key is
    # validated and the index is built after the transaction is committed
    op.execute(
        'ALTER TABLE build_tasks '
        'ADD CONSTRAINT build_tasks_build_node_id_fkey '
        'FOREIGN KEY (build_node_id) REFERENCES build_nodes (id) '
        'ON DELETE SET NULL NOT VALID'
    )
    with op.get_context().autocommit_block():
        op.execute(
            'ALTER TABLE build_tasks '
            'VALIDATE CONSTRAINT build_tasks_build_node_id_fkey'
        )
        op.create_index(
            op.f('ix_build_tasks_build_node_id'),
            'build_tasks',
            ['build_node_id'],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            op.f('ix_build_tasks_build_node_id'),
            table_name='build_tasks',
            postgresql_concurrently=True,
            if_exists=True,
        )
    op.drop_constraint(
        'build_tasks_build_node_id_fkey',
        'build_tasks',
        type_='foreignkey',
    )
    op.drop_column('build_tasks', 'queued_at')
    op.drop_column('build_tasks', 'node_reported_at')
    op.drop_column('build_tasks', 'claimed_at')
    op.drop_column('build_tasks', 'build_node_id')
    op.drop_table('build_nodes')
