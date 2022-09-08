"""Added timestamp for releases

Revision ID: 76855243a038
Revises: ec505e94fd1a
Create Date: 2022-09-07 16:10:50.954834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76855243a038'
down_revision = 'ec505e94fd1a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('build_releases', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.alter_column('build_releases', 'product_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('build_releases', 'product_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_column('build_releases', 'created_at')
    # ### end Alembic commands ###
