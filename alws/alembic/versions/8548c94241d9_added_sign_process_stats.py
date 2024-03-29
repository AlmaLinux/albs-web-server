"""Added sign process stats

Revision ID: 8548c94241d9
Revises: 4d3110a6e11d
Create Date: 2022-10-28 10:11:47.045697

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8548c94241d9'
down_revision = '722f5ac2f89e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('sign_tasks', sa.Column(
        'stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('sign_tasks', 'stats')
    # ### end Alembic commands ###
