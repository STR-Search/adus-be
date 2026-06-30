"""create_users_table

Revision ID: b7e9a21cb997
Revises: e9354841d49d
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e9a21cb997'
down_revision: Union[str, Sequence[str], None] = 'e9354841d49d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clerk_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=True),
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
        sa.UniqueConstraint("clerk_id"),
        schema="users",
    )
    op.create_index(
        "idx_users_clerk_id", "users", ["clerk_id"], unique=False, schema="users"
    )

    # Trigger to keep updated_at current on every row modification.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION users.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_updated_at
            BEFORE UPDATE ON users.users
            FOR EACH ROW EXECUTE FUNCTION users.update_updated_at();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS users_updated_at ON users.users;")
    op.execute("DROP FUNCTION IF EXISTS users.update_updated_at();")
    op.drop_index("idx_users_clerk_id", table_name="users", schema="users")
    op.drop_table("users", schema="users")
