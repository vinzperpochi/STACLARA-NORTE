"""Enforce case-insensitive username uniqueness."""

from alembic import op
import sqlalchemy as sa


revision = "c91d6a4b2e70"
down_revision = "f6b4d8e9c914"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            "SELECT lower(username), COUNT(*) FROM users "
            "GROUP BY lower(username) HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot enforce case-insensitive username uniqueness: existing accounts "
            f"share the name {duplicates[0]!r} (case-insensitive). Resolve the duplicate first."
        )
    op.create_index(
        "uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True
    )


def downgrade():
    op.drop_index("uq_users_username_lower", table_name="users")
