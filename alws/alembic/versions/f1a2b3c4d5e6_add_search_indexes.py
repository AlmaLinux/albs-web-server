"""Add indexes for search performance

Revision ID: f1a2b3c4d5e6
Revises: e9bb2a44defb
Create Date: 2026-04-07 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e9bb2a44defb"
branch_labels = None
depends_on = None


def upgrade():
    # Enable pg_trgm extension for GIN trigram indexes
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # BuildTaskRef: url and git_ref are used in LIKE queries for
    # project/ref search (crud/build.py:176,185-186).
    # pg_trgm GIN indexes support LIKE '%pattern%' efficiently.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_build_task_refs_url_trgm "
        "ON build_task_refs USING gin (url gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_build_task_refs_git_ref_trgm "
        "ON build_task_refs USING gin (git_ref gin_trgm_ops)"
    )

    # BuildTaskArtifact.href: used in IN() clause for RPM search
    # (crud/build.py:204)
    op.create_index(
        "idx_build_artifacts_href",
        "build_artifacts",
        ["href"],
        unique=False,
    )

    # Build columns used in WHERE filters (crud/build.py:180,209,211,214)
    op.create_index(
        "ix_builds_owner_id",
        "builds",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_builds_released",
        "builds",
        ["released"],
        unique=False,
    )
    op.create_index(
        "ix_builds_signed",
        "builds",
        ["signed"],
        unique=False,
    )
    op.create_index(
        "ix_builds_finished_at",
        "builds",
        ["finished_at"],
        unique=False,
    )

    # BuildTask.platform_id: used in filter (crud/build.py:190)
    op.create_index(
        "ix_build_tasks_platform_id",
        "build_tasks",
        ["platform_id"],
        unique=False,
    )

    # NewErrataRecord: title fields searched with LIKE
    # (crud/errata.py:1298-1299)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_errata_records_title_trgm "
        "ON new_errata_records USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_errata_records_original_title_trgm "
        "ON new_errata_records USING gin (original_title gin_trgm_ops)"
    )

    # NewErrataRecord.platform_id: used in filter (crud/errata.py:1303)
    op.create_index(
        "ix_new_errata_records_platform_id",
        "new_errata_records",
        ["platform_id"],
        unique=False,
    )

    # NewErrataRecord.release_status: used in filter (crud/errata.py:1310)
    op.create_index(
        "ix_new_errata_records_release_status",
        "new_errata_records",
        ["release_status"],
        unique=False,
    )

    # NewErrataRecord.issued_date: used in ORDER BY (crud/errata.py:1314)
    op.create_index(
        "ix_new_errata_records_issued_date",
        "new_errata_records",
        ["issued_date"],
        unique=False,
    )

    # NewErrataReference.cve_id: NewErrataRecord.cves is an
    # association_proxy through this column. The LIKE query in
    # crud/errata.py:1306 resolves to a subquery on cve_id.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_new_errata_references_cve_id_trgm "
        "ON new_errata_references USING gin (cve_id gin_trgm_ops)"
    )
    op.create_index(
        "ix_new_errata_references_cve_id",
        "new_errata_references",
        ["cve_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_new_errata_references_cve_id",
        table_name="new_errata_references",
    )
    op.execute("DROP INDEX IF EXISTS idx_new_errata_references_cve_id_trgm")
    op.drop_index("ix_new_errata_records_issued_date", table_name="new_errata_records")
    op.drop_index("ix_new_errata_records_release_status", table_name="new_errata_records")
    op.drop_index("ix_new_errata_records_platform_id", table_name="new_errata_records")
    op.execute("DROP INDEX IF EXISTS idx_errata_records_original_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_errata_records_title_trgm")
    op.drop_index("ix_build_tasks_platform_id", table_name="build_tasks")
    op.drop_index("ix_builds_finished_at", table_name="builds")
    op.drop_index("ix_builds_signed", table_name="builds")
    op.drop_index("ix_builds_released", table_name="builds")
    op.drop_index("ix_builds_owner_id", table_name="builds")
    op.drop_index("idx_build_artifacts_href", table_name="build_artifacts")
    op.execute("DROP INDEX IF EXISTS idx_build_task_refs_git_ref_trgm")
    op.execute("DROP INDEX IF EXISTS idx_build_task_refs_url_trgm")
