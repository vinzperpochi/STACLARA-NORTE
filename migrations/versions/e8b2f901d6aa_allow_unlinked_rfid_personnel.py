"""Allow RFID personnel registration before a web account is linked."""
from alembic import op
import sqlalchemy as sa

revision = 'e8b2f901d6aa'
down_revision = 'd7a91e8b420c'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('personnel_profiles') as batch:
        batch.alter_column('user_id', existing_type=sa.Integer(), nullable=True)
        for name,length in [('photo_filename',255),('department',100),('mobile',30),('email',255),('employment_status',40)]:
            batch.alter_column(name, existing_type=sa.String(length), nullable=True)


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT count(*) FROM personnel_profiles WHERE user_id IS NULL')).scalar():
        raise RuntimeError('Link personnel to web accounts before restoring the account requirement.')
    for name in ['photo_filename','department','mobile','email','employment_status']:
        if connection.execute(sa.text(f'SELECT count(*) FROM personnel_profiles WHERE {name} IS NULL')).scalar():
            raise RuntimeError('Complete optional personnel details before restoring the requirement.')
    with op.batch_alter_table('personnel_profiles') as batch:
        batch.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        for name,length in [('photo_filename',255),('department',100),('mobile',30),('email',255),('employment_status',40)]:
            batch.alter_column(name, existing_type=sa.String(length), nullable=False)
