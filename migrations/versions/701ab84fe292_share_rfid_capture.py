"""Store RFID registration sessions across Vercel instances."""

from alembic import op
import sqlalchemy as sa

revision = "701ab84fe292"
down_revision = "29a5911b2a7a"


def upgrade():
    op.create_table(
        "captures",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("expires", sa.Double(), nullable=False),
        sa.Column("ready", sa.Double()),
        sa.Column("digest", sa.Text()),
        sa.Column("suffix", sa.Text()),
        sa.Column("message", sa.Text()),
    )
    op.create_index("ix_captures_expires", "captures", ["expires"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE captures ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("captures")
