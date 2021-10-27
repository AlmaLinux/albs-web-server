"""add_sign_status

Revision ID: 1632f95e50b4
Revises: 2fb5ffc7ff29
Create Date: 2021-10-12 15:42:12.503594

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1632f95e50b4'
down_revision = '2fb5ffc7ff29'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "build_tasks",
        sa.Column(
            "sign_status", sa.Integer(), nullable=True
        ),
    )
    op.execute("UPDATE build_tasks SET sign_status=0")
    op.alter_column("build_tasks", "sign_status", nullable=False)


def downgrade():
    op.drop_column("build_tasks", "sign_status")
