"""Enforce one active RFID per personnel without altering existing assignments."""
from alembic import op
import sqlalchemy as sa

revision='f2a914c8b031'
down_revision='e8b2f901d6aa'
branch_labels=depends_on=None


def upgrade():
    connection=op.get_bind()
    duplicates=connection.execute(sa.text('SELECT personnel_id FROM rfid_cards WHERE active = true GROUP BY personnel_id HAVING count(*) > 1')).first()
    if duplicates:
        raise RuntimeError('Multiple active RFID cards exist for one personnel record. Choose the intended card and revoke the others before applying this constraint; no records have been changed.')
    op.create_index('uq_rfid_one_active_personnel','rfid_cards',['personnel_id'],unique=True,postgresql_where=sa.text('active IS TRUE'),sqlite_where=sa.text('active IS 1'))


def downgrade():
    op.drop_index('uq_rfid_one_active_personnel',table_name='rfid_cards')
