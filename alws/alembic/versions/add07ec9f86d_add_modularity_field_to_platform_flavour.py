"""Add modularity field to platform flavour

Revision ID: add07ec9f86d
Revises: 5c3da459c12f
Create Date: 2022-04-01 09:01:18.954893

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "add07ec9f86d"
down_revision = "077264687344"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "platform_flavours",
        sa.Column("modularity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("platform_flavours", "modularity")
    # ### end Alembic commands ###
