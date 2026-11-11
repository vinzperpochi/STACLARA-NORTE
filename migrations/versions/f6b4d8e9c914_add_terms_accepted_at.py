"""Add terms_accepted_at to User model

Revision ID: f6b4d8e9c914
Revises: e5a2c9f13b07
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b4d8e9c914'
down_revision = 'e5a2c9f13b07'
branch_labels = None
depends_on = None


def upgrade():
    # Add terms_accepted_at column to users table
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remove terms_accepted_at column from users table
    op.drop_column('users', 'terms_accepted_at')
