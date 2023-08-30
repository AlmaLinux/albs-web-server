"""Create table for test repositories

Revision ID: b924266af778
Revises: cd510df3fa78
Create Date: 2023-08-17 09:30:35.125229

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b924266af778'
down_revision = 'cd510df3fa78'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('test_repositories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('tests_dir', sa.Text(), nullable=False),
    sa.Column('tests_prefix', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('url')
    )
    op.create_table('package_test_repository',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('package_name', sa.Text(), nullable=False),
    sa.Column('folder_name', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('test_repository_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['test_repository_id'], ['test_repositories.id'], name='fk_package_test_repository_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('package_test_repository')
    op.drop_table('test_repositories')
    # ### end Alembic commands ###
