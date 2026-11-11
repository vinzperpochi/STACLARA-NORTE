"""add document request workflow and requirements

Revision ID: 42253b4a95b6
Revises: 257cf6dbe79c
"""
from alembic import op
import sqlalchemy as sa

revision = "42253b4a95b6"
down_revision = "257cf6dbe79c"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("issued_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("request_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint("uq_issued_documents_request", ["request_id"])
        batch_op.create_foreign_key("fk_issued_documents_request", "requests", ["request_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("document_type_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("additional_requirements_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("generated_filename", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_requests_document_type_id", ["document_type_id"], unique=False)
        batch_op.create_foreign_key("fk_requests_reviewed_by", "users", ["reviewed_by_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_requests_document_type", "document_types", ["document_type_id"], ["id"], ondelete="RESTRICT")
    op.create_table(
        "document_requirements",
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("requirement_name", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], name="fk_document_requirements_request", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name="fk_document_requirements_uploaded_by", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_requirements_request_status", "document_requirements", ["request_id", "status"], unique=False)
    op.create_index("ix_document_requirements_status", "document_requirements", ["status"], unique=False)
    op.create_table(
        "document_request_events",
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"], name="fk_document_request_events_changed_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], name="fk_document_request_events_request", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_request_events_request_created", "document_request_events", ["request_id", "created_at"], unique=False)


def downgrade():
    op.drop_index("ix_document_request_events_request_created", table_name="document_request_events")
    op.drop_table("document_request_events")
    op.drop_index("ix_document_requirements_status", table_name="document_requirements")
    op.drop_index("ix_document_requirements_request_status", table_name="document_requirements")
    op.drop_table("document_requirements")
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_constraint("fk_requests_document_type", type_="foreignkey")
        batch_op.drop_constraint("fk_requests_reviewed_by", type_="foreignkey")
        batch_op.drop_index("ix_requests_document_type_id")
        for column in ("released_at", "ready_at", "generated_at", "generated_filename", "reviewed_at", "reviewed_by_id", "additional_requirements_note", "rejection_reason", "document_type_id"):
            batch_op.drop_column(column)
    with op.batch_alter_table("issued_documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_issued_documents_request", type_="foreignkey")
        batch_op.drop_constraint("uq_issued_documents_request", type_="unique")
        batch_op.drop_column("request_id")
