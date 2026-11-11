"""add centralized request queue and collections
Revision ID: 5a7c3e91d204
Revises: 4f2b9a8c1d77
"""
from alembic import op
import sqlalchemy as sa
revision = "5a7c3e91d204"
down_revision = "4f2b9a8c1d77"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("queue_requests",
        sa.Column("queue_number", sa.String(length=50), nullable=False), sa.Column("resident_id", sa.Integer(), nullable=False), sa.Column("request_type", sa.String(length=40), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("appointment_date", sa.Date(), nullable=True), sa.Column("appointment_time", sa.Time(), nullable=True), sa.Column("assigned_official_id", sa.Integer(), nullable=True), sa.Column("remarks", sa.Text(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["assigned_official_id"], ["users.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("queue_number"))
    op.create_index("ix_queue_requests_status_date", "queue_requests", ["status", "appointment_date"])
    op.create_index("ix_queue_requests_resident", "queue_requests", ["resident_id"])
    op.create_table("collection_entries",
        sa.Column("transaction_number", sa.String(length=50), nullable=False), sa.Column("resident_id", sa.Integer(), nullable=False), sa.Column("service", sa.String(length=150), nullable=False), sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False), sa.Column("payment_method", sa.String(length=40), nullable=False), sa.Column("transaction_date", sa.Date(), nullable=False), sa.Column("receiving_official_id", sa.Integer(), nullable=True), sa.Column("reference_number", sa.String(length=100), nullable=True), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["receiving_official_id"], ["users.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("transaction_number", name="uq_collection_entries_transaction"))
    op.create_index("ix_collection_entries_date_service", "collection_entries", ["transaction_date", "service"])

def downgrade():
    op.drop_table("collection_entries")
    op.drop_table("queue_requests")
