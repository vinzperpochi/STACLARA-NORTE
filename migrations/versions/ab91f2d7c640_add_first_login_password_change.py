"""add first-login password change flag

Revision ID: ab91f2d7c640
Revises: 8e2c6b40d915
Create Date: 2026-09-28 01:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "ab91f2d7c640"
down_revision = "8e2c6b40d915"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("must_change_password", server_default=None)


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("must_change_password")
