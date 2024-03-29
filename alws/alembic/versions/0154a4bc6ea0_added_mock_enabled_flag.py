"""Added mock_enabled flag

Revision ID: 0154a4bc6ea0
Revises: 76855243a038
Create Date: 2022-10-17 08:45:04.255793

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0154a4bc6ea0'
down_revision = '76855243a038'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('repositories', sa.Column('mock_enabled', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('repositories', 'mock_enabled')
    # ### end Alembic commands ###
