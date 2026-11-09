"""Add an index on build_artifacts.href

Revision ID: b7c1d2e3f4a5
Revises: 9ca5afd67819
Create Date: 2026-11-09 15:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b7c1d2e3f4a5'
down_revision = '9ca5afd67819'
branch_labels = None
depends_on = None


def upgrade():
    # build_artifacts is big and gets new rows all the time, so build the
    # index without locking writes; CONCURRENTLY can't run in a transaction
    with op.get_context().autocommit_block():
        op.create_index(
            op.f('ix_build_artifacts_href'),
            'build_artifacts',
            ['href'],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            op.f('ix_build_artifacts_href'),
            table_name='build_artifacts',
            postgresql_concurrently=True,
            if_exists=True,
        )
