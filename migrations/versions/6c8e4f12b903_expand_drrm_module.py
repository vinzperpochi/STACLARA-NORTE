"""expand drrm module
Revision ID: 6c8e4f12b903
Revises: 5a7c3e91d204
"""
from alembic import op
import sqlalchemy as sa
revision = "6c8e4f12b903"
down_revision = "5a7c3e91d204"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("evacuation_centers", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column("evacuation_centers", sa.Column("facilities", sa.Text(), nullable=True))
    op.add_column("evacuation_centers", sa.Column("current_status", sa.String(length=40), nullable=False, server_default="AVAILABLE"))
    for name, column in [("incident_date", sa.Date()), ("location", sa.String(length=255)), ("damage_assessment", sa.Text()), ("response_actions", sa.Text())]:
        op.add_column("drrm_incidents", sa.Column(name, column, nullable=True))
    for name in ("affected_households", "injuries", "deaths"):
        op.add_column("drrm_incidents", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.create_table("emergency_contacts", sa.Column("name", sa.String(length=150), nullable=False), sa.Column("agency", sa.String(length=150), nullable=True), sa.Column("contact_number", sa.String(length=50), nullable=False), sa.Column("role", sa.String(length=120), nullable=True), sa.Column("availability_notes", sa.Text(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_table("drrm_equipment", sa.Column("name", sa.String(length=150), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("condition", sa.String(length=50), nullable=False), sa.Column("storage_location", sa.String(length=200), nullable=True), sa.Column("notes", sa.Text(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_drrm_equipment_status", "drrm_equipment", ["status"])
    op.create_table("relief_supplies", sa.Column("name", sa.String(length=150), nullable=False), sa.Column("quantity_on_hand", sa.Numeric(precision=12, scale=2), nullable=False), sa.Column("unit", sa.String(length=40), nullable=False), sa.Column("storage_location", sa.String(length=200), nullable=True), sa.Column("expiry_date", sa.Date(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("name"))
    op.create_table("drrm_damage_reports", sa.Column("incident_id", sa.Integer(), nullable=False), sa.Column("household_id", sa.Integer(), nullable=True), sa.Column("property_description", sa.Text(), nullable=False), sa.Column("estimated_cost", sa.Numeric(precision=12, scale=2), nullable=True), sa.Column("assessment_notes", sa.Text(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["incident_id"], ["drrm_incidents.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_table("emergency_alerts", sa.Column("title", sa.String(length=200), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("alert_level", sa.String(length=30), nullable=False), sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True), sa.Column("issued_by_id", sa.Integer(), nullable=True), sa.Column("status", sa.String(length=50), nullable=False), sa.Column("id", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False), sa.ForeignKeyConstraint(["issued_by_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))

def downgrade():
    for table in ("emergency_alerts", "drrm_damage_reports", "relief_supplies", "drrm_equipment", "emergency_contacts"):
        op.drop_table(table)
    for name in ("deaths", "injuries", "affected_households", "response_actions", "damage_assessment", "location", "incident_date"):
        op.drop_column("drrm_incidents", name)
    for name in ("current_status", "facilities", "location"):
        op.drop_column("evacuation_centers", name)
