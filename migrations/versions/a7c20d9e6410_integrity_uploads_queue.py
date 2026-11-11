"""Normalized Purok identity, profile images and exact blotter fingerprints.

Preflight refuses ambiguous legacy duplicates; no records are silently deleted.
"""
from alembic import op
import sqlalchemy as sa
from app.normalization import purok_identity

revision = 'a7c20d9e6410'
down_revision = 'f6b4d8e9c914'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text('SELECT id, name FROM puroks ORDER BY id')).mappings().all()
    normalized = []
    names, numbers = {}, {}
    for row in rows:
        name, key, number = purok_identity(row['name'])
        conflicts = [names[key]] if key in names else []
        if number is not None and number in numbers:
            conflicts.append(numbers[number])
        if conflicts:
            raise RuntimeError(f"Purok duplicate IDs {sorted(set(conflicts + [row['id']]))}: review and consolidate references with a backup before migrating; no data was deleted.")
        names[key] = row['id']
        if number is not None:
            numbers[number] = row['id']
        normalized.append({'id': row['id'], 'name': name, 'key': key, 'number': number})
    with op.batch_alter_table('puroks') as batch:
        batch.add_column(sa.Column('name_key', sa.String(100), nullable=True))
        batch.add_column(sa.Column('purok_number', sa.Integer(), nullable=True))
    for row in normalized:
        bind.execute(sa.text('UPDATE puroks SET name=:name, name_key=:key, purok_number=:number WHERE id=:id'), row)
    with op.batch_alter_table('puroks') as batch:
        batch.alter_column('name_key', existing_type=sa.String(100), nullable=False)
        batch.create_unique_constraint('uq_puroks_name_key', ['name_key'])
        batch.create_unique_constraint('uq_puroks_number', ['purok_number'])
        batch.create_check_constraint('ck_puroks_normalized', "name_key = lower(name) AND name = trim(name) AND name NOT LIKE '%  %'")
        batch.create_check_constraint('ck_puroks_name_length', 'length(name) >= 2 AND length(name) <= 100')
        batch.create_check_constraint('ck_puroks_number_range', 'purok_number IS NULL OR (purok_number >= 1 AND purok_number <= 9999)')
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('profile_photo_filename', sa.String(255)))
    with op.batch_alter_table('blotter_cases') as batch:
        batch.add_column(sa.Column('incident_fingerprint', sa.String(64)))
        batch.create_unique_constraint('uq_blotter_cases_incident_fingerprint', ['incident_fingerprint'])
        batch.create_index('ix_blotter_cases_status_queue', ['status', 'id'])
    # Legacy cases retain their reference and identity. Do not merge historical cases.


def downgrade():
    with op.batch_alter_table('blotter_cases') as batch:
        batch.drop_index('ix_blotter_cases_status_queue')
        batch.drop_constraint('uq_blotter_cases_incident_fingerprint', type_='unique')
        batch.drop_column('incident_fingerprint')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('profile_photo_filename')
    with op.batch_alter_table('puroks') as batch:
        batch.drop_constraint('ck_puroks_number_range', type_='check')
        batch.drop_constraint('ck_puroks_name_length', type_='check')
        batch.drop_constraint('ck_puroks_normalized', type_='check')
        batch.drop_constraint('uq_puroks_number', type_='unique')
        batch.drop_constraint('uq_puroks_name_key', type_='unique')
        batch.drop_column('purok_number')
        batch.drop_column('name_key')
