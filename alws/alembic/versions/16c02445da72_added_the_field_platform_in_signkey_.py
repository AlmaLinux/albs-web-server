"""Added the field platform in signkey table

Revision ID: 16c02445da72
Revises: 284da0d3ed87
Create Date: 2022-01-24 05:49:19.149424

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16c02445da72'
down_revision = '284da0d3ed87'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('sign_keys', sa.Column('platform_id', sa.Integer(), nullable=True))
    op.create_foreign_key('sign_keys_platform_id_fkey', 'sign_keys', 'platforms', ['platform_id'], ['id'])
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('sign_keys_platform_id_fkey', 'sign_keys', type_='foreignkey')
    op.drop_column('sign_keys', 'platform_id')
    # ### end Alembic commands ###
