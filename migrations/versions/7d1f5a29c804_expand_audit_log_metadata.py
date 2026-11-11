"""expand audit log metadata
Revision ID: 7d1f5a29c804
Revises: 6c8e4f12b903
"""
from alembic import op
import sqlalchemy as sa
revision = "7d1f5a29c804"
down_revision = "6c8e4f12b903"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("audit_logs", sa.Column("role", sa.String(length=100), nullable=True))
    op.add_column("audit_logs", sa.Column("module", sa.String(length=100), nullable=True))
    op.add_column("audit_logs", sa.Column("description", sa.String(length=2000), nullable=True))

def downgrade():
    op.drop_column("audit_logs", "description")
    op.drop_column("audit_logs", "module")
    op.drop_column("audit_logs", "role")
