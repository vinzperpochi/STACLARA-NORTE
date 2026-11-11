"""add optional incident coordinates to blotter cases

Revision ID: e5a2c9f13b07
Revises: c31a8f7e2b11, d4e9a1c73b58
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa


revision = "e5a2c9f13b07"
down_revision = ("c31a8f7e2b11", "d4e9a1c73b58")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("blotter_cases")}
    if "incident_latitude" not in existing:
        op.add_column("blotter_cases", sa.Column("incident_latitude", sa.Numeric(10, 6), nullable=True))
    if "incident_longitude" not in existing:
        op.add_column("blotter_cases", sa.Column("incident_longitude", sa.Numeric(10, 6), nullable=True))


def downgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("blotter_cases")}
    if "incident_longitude" in existing:
        op.drop_column("blotter_cases", "incident_longitude")
    if "incident_latitude" in existing:
        op.drop_column("blotter_cases", "incident_latitude")
