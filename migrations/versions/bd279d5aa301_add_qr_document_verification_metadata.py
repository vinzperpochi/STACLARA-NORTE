"""add QR document verification metadata

Revision ID: bd279d5aa301
Revises: 42253b4a95b6
"""
import base64
from io import BytesIO

import qrcode
import sqlalchemy as sa
from alembic import op

revision = "bd279d5aa301"
down_revision = "42253b4a95b6"
branch_labels = None
depends_on = None


def _qr_data_uri(value: str) -> str:
    image = qrcode.make(value)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def upgrade():
    with op.batch_alter_table("document_types", schema=None) as batch_op:
        batch_op.add_column(sa.Column("validity_days", sa.Integer(), nullable=True))
    with op.batch_alter_table("issued_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("authorized_signatory", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("verification_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("qr_code_data_uri", sa.Text(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, document_number FROM issued_documents")).mappings().all()
    for row in rows:
        url = f"/verify/{row['document_number']}"
        connection.execute(sa.text("UPDATE issued_documents SET authorized_signatory=:signatory, verification_url=:url, qr_code_data_uri=:qr WHERE id=:id"), {"signatory": "Punong Barangay", "url": url, "qr": _qr_data_uri(url), "id": row["id"]})

    with op.batch_alter_table("issued_documents", schema=None) as batch_op:
        batch_op.alter_column("authorized_signatory", existing_type=sa.String(length=200), nullable=False)
        batch_op.alter_column("verification_url", existing_type=sa.String(length=500), nullable=False)
        batch_op.alter_column("qr_code_data_uri", existing_type=sa.Text(), nullable=False)


def downgrade():
    with op.batch_alter_table("issued_documents", schema=None) as batch_op:
        batch_op.drop_column("qr_code_data_uri")
        batch_op.drop_column("verification_url")
        batch_op.drop_column("authorized_signatory")
    with op.batch_alter_table("document_types", schema=None) as batch_op:
        batch_op.drop_column("validity_days")
