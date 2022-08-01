"""Removed Distributions

Revision ID: 26b384d3493f
Revises: 9c9b0fdc1a7f
Create Date: 2022-07-27 15:35:12.334677

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "26b384d3493f"
down_revision = "9c9b0fdc1a7f"
branch_labels = None
depends_on = None


def upgrade():

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("distribution_repositories")
    op.drop_table("distribution_packages")
    op.drop_table("platform_dependency")
    op.drop_index("ix_distributions_name", table_name="distributions")
    op.drop_table("distributions")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "distributions",
        sa.Column(
            "id",
            sa.INTEGER(),
            server_default=sa.text("nextval('distributions_id_seq'::regclass)"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("name", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("permissions", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("owner_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("team_id", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="distributions_owner_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="distributions_team_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="distributions_pkey"),
        postgresql_ignore_search_path=False,
    )
    op.create_index("ix_distributions_name", "distributions", ["name"], unique=False)
    op.create_table(
        "platform_dependency",
        sa.Column("distribution_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("platform_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["distribution_id"],
            ["distributions.id"],
            name="platform_dependency_distribution_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["platforms.id"],
            name="platform_dependency_platform_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "distribution_id", "platform_id", name="platform_dependency_pkey"
        ),
    )
    op.create_table(
        "distribution_packages",
        sa.Column("distribution_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("build_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["build_id"], ["builds.id"], name="distribution_packages_build_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["distribution_id"],
            ["distributions.id"],
            name="distribution_packages_distribution_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "distribution_id", "build_id", name="distribution_packages_pkey"
        ),
    )
    op.create_table(
        "distribution_repositories",
        sa.Column("distribution_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("repository_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["distribution_id"],
            ["distributions.id"],
            name="distribution_repositories_distribution_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name="distribution_repositories_repository_id_fkey",
        ),
        sa.PrimaryKeyConstraint(
            "distribution_id", "repository_id", name="distribution_repositories_pkey"
        ),
    )
    # ### end Alembic commands ###
