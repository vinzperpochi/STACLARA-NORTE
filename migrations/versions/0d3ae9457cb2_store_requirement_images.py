"""Store uploaded requirement images with their request."""

from alembic import op
import sqlalchemy as sa

revision = "0d3ae9457cb2"
down_revision = "701ab84fe292"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_requirements", sa.Column("image_data", sa.LargeBinary()))
    op.add_column("complaint_evidence", sa.Column("file_data", sa.LargeBinary()))


def downgrade():
    op.drop_column("complaint_evidence", "file_data")
    op.drop_column("document_requirements", "image_data")
