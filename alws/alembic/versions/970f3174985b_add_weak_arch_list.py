"""Add weak arch list

Revision ID: 970f3174985b
Revises: 7469773f4f79
Create Date: 2022-03-16 19:20:17.748806

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "970f3174985b"
down_revision = "7469773f4f79"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "platforms",
        sa.Column(
            "weak_arch_list", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("platforms", "weak_arch_list")
    # ### end Alembic commands ###
