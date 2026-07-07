"""create_api_keys_table

Revision ID: c4d5e6f7a8b9
Revises: b7e9a21cb997
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b7e9a21cb997'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"]),
        schema="users",
    )
    op.create_index(
        "idx_api_keys_key_hash", "api_keys", ["key_hash"], unique=True, schema="users"
    )
    op.create_index(
        "idx_api_keys_user_id", "api_keys", ["user_id"], unique=False, schema="users"
    )

    # Reuse the users.update_updated_at() function created in the users table
    # migration; add a trigger to keep updated_at current on every modification.
    op.execute(
        """
        CREATE TRIGGER api_keys_updated_at
            BEFORE UPDATE ON users.api_keys
            FOR EACH ROW EXECUTE FUNCTION users.update_updated_at();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS api_keys_updated_at ON users.api_keys;")
    op.drop_index("idx_api_keys_user_id", table_name="api_keys", schema="users")
    op.drop_index("idx_api_keys_key_hash", table_name="api_keys", schema="users")
    op.drop_table("api_keys", schema="users")
