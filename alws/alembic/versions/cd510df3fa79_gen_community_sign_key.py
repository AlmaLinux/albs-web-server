"""Gen community sign key

Revision ID: cd510df3fa79
Revises: cd510df3fa78
Create Date: 2023-06-22 12:35:00.000000

"""
import sqlalchemy as sa
from alembic import op

from alws.constants import GenKeyStatus

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
    op.add_column(
        'sign_keys',
        sa.Column('product_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'sign_keys_product_id_fkey',
        'sign_keys',
        'products',
        ['product_id'],
        ['id'],
    )
    op.create_table(
        'gen_key_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Integer(), default=GenKeyStatus.IDLE),
        sa.Column('error_message', sa.TEXT(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name='gen_key_task_product_id_fkey'
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_constraint(
        'sign_keys_product_id_fkey',
        'sign_keys',
        type_='foreignkey',
    )
    op.drop_column('sign_keys', 'is_community')
    op.drop_column('sign_keys', 'product_id')
    op.drop_table('gen_key_tasks')
