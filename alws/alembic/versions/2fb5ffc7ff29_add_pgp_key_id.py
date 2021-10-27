"""add_pgp_key_id

Revision ID: 2fb5ffc7ff29
Revises: 76eec955d203
Create Date: 2021-10-12 15:33:10.230841

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2fb5ffc7ff29'
down_revision = '38cb9a229d07'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "builds",
        sa.Column(
            "pgp_key_id", sa.Text(), nullable=True
        ),
    )


def downgrade():
    op.drop_column("builds", "pgp_key_id")
