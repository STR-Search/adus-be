"""create_saved_searches_table

Revision ID: f1a4d7b62c30
Revises: c4d5e6f7a8b9
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a4d7b62c30"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("query_string", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "resource", "name", name="uq_saved_searches_user_resource_name"
        ),
        schema="users",
    )
    op.create_index(
        "idx_saved_searches_user_id_resource",
        "saved_searches",
        ["user_id", "resource"],
        unique=False,
        schema="users",
    )

    op.execute("""
        CREATE TRIGGER saved_searches_updated_at
            BEFORE UPDATE ON users.saved_searches
            FOR EACH ROW EXECUTE FUNCTION users.update_updated_at();
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS saved_searches_updated_at ON users.saved_searches;"
    )
    op.drop_index(
        "idx_saved_searches_user_id_resource",
        table_name="saved_searches",
        schema="users",
    )
    op.drop_table("saved_searches", schema="users")
