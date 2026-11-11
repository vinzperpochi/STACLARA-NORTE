"""expand_token_columns_add_github_id

Fix: reset_token_hash and activation_token_hash columns were String(128),
too short for werkzeug scrypt hashes (~162 chars). Expanded to String(255).
Added github_id column for GitHub OAuth login.

Revision ID: 29a5911b2a7a
Revises: f2a914c8b031
Create Date: 2026-11-11 22:17:32.589816

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '29a5911b2a7a'
down_revision = 'f2a914c8b031'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Expand token hash columns that were too short for scrypt hashes
        batch_op.alter_column(
            'activation_token_hash',
            existing_type=sa.VARCHAR(length=128),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'reset_token_hash',
            existing_type=sa.VARCHAR(length=128),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
        # Add GitHub OAuth identifier column
        batch_op.add_column(sa.Column('github_id', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_users_github_id', ['github_id'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_github_id', type_='unique')
        batch_op.drop_column('github_id')
        batch_op.alter_column(
            'reset_token_hash',
            existing_type=sa.String(length=255),
            type_=sa.VARCHAR(length=128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'activation_token_hash',
            existing_type=sa.String(length=255),
            type_=sa.VARCHAR(length=128),
            existing_nullable=True,
        )
