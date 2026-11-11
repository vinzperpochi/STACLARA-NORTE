"""add business and health social welfare registries
Revision ID: 4f2b9a8c1d77
Revises: 32386991b14f
"""
from alembic import op
import sqlalchemy as sa
revision = "4f2b9a8c1d77"
down_revision = "32386991b14f"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("business_records",
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("business_address", sa.String(length=255), nullable=False),
        sa.Column("business_type", sa.String(length=150), nullable=False),
        sa.Column("registration_date", sa.Date(), nullable=False),
        sa.Column("permit_number", sa.String(length=80), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["residents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("permit_number"))
    op.create_index("ix_business_records_status_expiration", "business_records", ["status", "expiration_date"])
    op.create_table("business_clearance_requests",
        sa.Column("request_number", sa.String(length=50), nullable=False), sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False), sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True), sa.Column("reviewed_by_id", sa.Integer(), nullable=True), sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["business_records.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["requester_id"], ["residents.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("request_number"))
    op.create_index("ix_business_clearance_requests_status_created", "business_clearance_requests", ["status", "created_at"])
    op.create_table("beneficiary_registry",
        sa.Column("resident_id", sa.Integer(), nullable=False), sa.Column("category", sa.String(length=40), nullable=False), sa.Column("application_status", sa.String(length=30), nullable=False), sa.Column("registered_date", sa.Date(), nullable=False), sa.Column("application_notes", sa.Text(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_beneficiary_registry_category_status", "beneficiary_registry", ["category", "status"])
    op.create_table("assistance_records",
        sa.Column("beneficiary_id", sa.Integer(), nullable=False), sa.Column("assistance_type", sa.String(length=120), nullable=False), sa.Column("assistance_date", sa.Date(), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("description", sa.Text(), nullable=True), sa.Column("distribution_officer_id", sa.Integer(), nullable=True), sa.Column("remarks", sa.Text(), nullable=True), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiary_registry.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["distribution_officer_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_assistance_records_date", "assistance_records", ["assistance_date"])

def downgrade():
    op.drop_table("assistance_records")
    op.drop_table("beneficiary_registry")
    op.drop_table("business_clearance_requests")
    op.drop_table("business_records")
