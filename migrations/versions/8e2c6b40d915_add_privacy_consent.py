"""add privacy consent metadata
Revision ID: 8e2c6b40d915
Revises: 7d1f5a29c804
"""
from alembic import op
import sqlalchemy as sa
revision = "8e2c6b40d915"
down_revision = "7d1f5a29c804"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("privacy_consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("privacy_consent_version", sa.String(length=30), nullable=True))

def downgrade():
    op.drop_column("users", "privacy_consent_version")
    op.drop_column("users", "privacy_consent_at")
