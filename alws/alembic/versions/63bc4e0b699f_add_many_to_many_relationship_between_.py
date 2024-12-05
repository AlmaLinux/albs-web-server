"""Add many to many relationship between platforms and sign_keys

Revision ID: 63bc4e0b699f
Revises: 764a67b23038
Create Date: 2024-11-01 12:26:26.326314

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = '63bc4e0b699f'
down_revision = '9977cc722e24'
branch_labels = None
depends_on = None


def disable_fk_checks():
    op.execute(sa.text("SET session_replication_role = 'replica'"))

def enable_fk_checks():
    op.execute(sa.text("SET session_replication_role = 'origin'"))

def get_columns(table_name):
    # Use SQLAlchemy's Inspector to retrieve the columns of the specified table
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return columns


def create_backup_table(table_name):
    backup_table = f'{table_name}_backup'
    op.execute(
        sa.text(f"CREATE TABLE {backup_table} AS TABLE {table_name} WITH DATA")
    )


def drop_backup_table(backup_table_name):
    op.execute(sa.text(f"DROP TABLE IF EXISTS {backup_table_name}"))


def restore_from_backup(table_name):
    backup_table = f'{table_name}_backup'
    columns = get_columns(table_name)
    column_list = ', '.join(columns)
    disable_fk_checks()
    op.execute(sa.text(f"DELETE FROM {table_name}"))
    op.execute(
        sa.text(
            f"INSERT INTO {table_name} ({column_list}) SELECT {column_list} FROM {backup_table}"
        )
    )
    enable_fk_checks()


def create_association_table():
    op.create_table(
        'platforms_sign_keys',
        sa.Column(
            'platform_id',
            sa.Integer,
            sa.ForeignKey('platforms.id', ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            'sign_key_id',
            sa.Integer,
            sa.ForeignKey('sign_keys.id', ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def upgrade():
    create_backup_table("platforms")
    create_backup_table("sign_keys")
    op.drop_constraint(
        'sign_keys_platform_id_fkey', 'sign_keys', type_='foreignkey'
    )
    create_association_table()
    op.execute(
        sa.text(
            """
        INSERT INTO platforms_sign_keys (platform_id, sign_key_id)
        SELECT platform_id, id FROM sign_keys
        WHERE platform_id IS NOT NULL
    """
        )
    )
    op.drop_column("sign_keys", "platform_id")


def downgrade():
    op.add_column(
        "sign_keys", sa.Column("platform_id", sa.Integer, nullable=True)
    )
    op.execute(
        sa.text(
            """
        UPDATE sign_keys
        SET platform_id = (
            SELECT platform_id
            FROM platforms_sign_keys
            WHERE platforms_sign_keys.sign_key_id = sign_keys.id
            LIMIT 1
        )
    """
        )
    )
    op.create_foreign_key(
        'sign_keys_platform_id_fkey',
        'sign_keys',
        'platforms',
        ['platform_id'],
        ['id'],
    )
    op.drop_table('platforms_sign_keys')

    restore_from_backup("platforms")
    restore_from_backup("sign_keys")

    # Neccessary to preserve id sequences
    op.execute(
        sa.text(
            """
            SELECT setval('platforms_id_seq', MAX(id)) FROM platforms;
            """
        )
    )
    op.execute(
        sa.text(
            """
            SELECT setval('sign_keys_id_seq', MAX(id)) FROM sign_keys;
            """
        )
    )

    drop_backup_table("platforms_backup")
    drop_backup_table("sign_keys_backup")
