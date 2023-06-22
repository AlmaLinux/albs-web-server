"""Gen community sign key

Revision ID: cd510df3fa79
Revises: cd510df3fa78
Create Date: 2023-06-22 12:35:00.000000

"""
import sqlalchemy as sa
from alembic import op

from alws.constants import SignStatus

# revision identifiers, used by Alembic.
revision = 'cd510df3fa79'
down_revision = 'cd510df3fa78'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sign_keys',
        sa.Column('is_community', sa.Boolean(), nullable=True, default=True),
    )
    op.create_table(
        'gen_key_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Boolean, default=SignStatus.IDLE),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["products_id"],
            ["products.id"],
            name='gen_key_task_product_id'
        ),
        sa.ForeignKeyConstraint(
            ["platforms_id"],
            ["platforms.id"],
            name='gen_key_task_platform_id'
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_column('sign_tasks', 'is_community')
    op.drop_table('sign_keys')
