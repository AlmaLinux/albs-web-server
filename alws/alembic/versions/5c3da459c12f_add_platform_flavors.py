"""add platform flavors

Revision ID: 5c3da459c12f
Revises: 970f3174985b
Create Date: 2022-03-30 21:19:39.065037

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c3da459c12f"
down_revision = "970f3174985b"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "platform_flavours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "platform_flavour_repository",
        sa.Column("flavour_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["flavour_id"],
            ["platform_flavours.id"],
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
        ),
        sa.PrimaryKeyConstraint("flavour_id", "repository_id"),
    )
    op.create_table(
        "build_platform_flavour",
        sa.Column("flavour_id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["builds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["flavour_id"],
            ["platform_flavours.id"],
        ),
        sa.PrimaryKeyConstraint("flavour_id", "build_id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("build_platform_flavour")
    op.drop_table("platform_flavour_repository")
    op.drop_table("platform_flavours")
    # ### end Alembic commands ###
