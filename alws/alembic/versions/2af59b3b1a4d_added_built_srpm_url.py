"""Added built srpm url

Revision ID: 2af59b3b1a4d
Revises: 601fc733a869
Create Date: 2022-01-21 07:12:22.956018

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2af59b3b1a4d'
down_revision = '601fc733a869'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('build_tasks', sa.Column('built_srpm_url', sa.VARCHAR(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('build_tasks', 'built_srpm_url')
    # ### end Alembic commands ###
