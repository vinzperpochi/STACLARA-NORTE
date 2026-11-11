"""add email verification timestamp

Revision ID: d4e9a1c73b58
Revises: ab91f2d7c640
Create Date: 2026-09-28 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e9a1c73b58"
down_revision = "ab91f2d7c640"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verified_at")
