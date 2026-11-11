"""Exercise migrations only on a new disposable local SQLite database."""
import os
import sys
from pathlib import Path
from uuid import uuid4
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
scratch = root / '.migration-qa' / uuid4().hex
scratch.mkdir(parents=True)
os.environ['DATABASE_URL'] = 'sqlite:///' + (scratch/'database.sqlite').as_posix()
os.environ['STORAGE_ROOT'] = str(scratch)
os.environ['LOG_FILE'] = str(scratch/'migration.log')
from app import create_app
from app.extensions import db
from flask_migrate import upgrade, downgrade
from sqlalchemy import text, inspect
app = create_app('development')
with app.app_context():
    upgrade(directory=str(root/'migrations'), revision='heads')
    columns = {column['name'] for column in inspect(db.engine).get_columns('residents')}
    assert {'place_of_birth', 'proof_of_residency_filename', 'special_categories', 'emergency_contact_number'} <= columns
    assert db.session.execute(text('SELECT version_num FROM alembic_version')).scalar() == 'c9e42a15d831'
    assert {'document_sequences','document_signatories'} <= set(inspect(db.engine).get_table_names())
    print('Fresh full upgrade: PASS')
    downgrade(directory=str(root/'migrations'), revision='f6b4d8e9c914')
    db.session.execute(text("INSERT INTO puroks (name,status,created_at,updated_at) VALUES ('Purok 01','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(' PUROK 1 ','active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    db.session.commit()
    try:
        upgrade(directory=str(root/'migrations'), revision='heads')
    except (RuntimeError, SystemExit):
        db.session.rollback()
    else:
        raise AssertionError('Ambiguous duplicates must stop migration')
    assert db.session.execute(text('SELECT COUNT(*) FROM puroks')).scalar() == 2
    print('Duplicate preflight preserves records: PASS')
    db.session.execute(text("DELETE FROM puroks WHERE name=' PUROK 1 '"))
    db.session.execute(text("INSERT INTO households (household_number,address_line,purok_id,status,created_at,updated_at) VALUES ('QA-HH','QA address',1,'active',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    db.session.commit()
    upgrade(directory=str(root/'migrations'), revision='heads')
    assert db.session.execute(text('SELECT name,name_key,purok_number FROM puroks')).one() == ('Purok 1','purok 1',1)
    assert db.session.execute(text('SELECT purok_id FROM households')).scalar() == 1
    assert db.session.execute(text('PRAGMA foreign_key_check')).all() == []
    print('Canonical backfill and linked references: PASS')
    downgrade(directory=str(root/'migrations'), revision='f6b4d8e9c914')
    upgrade(directory=str(root/'migrations'), revision='heads')
    assert db.session.execute(text('PRAGMA foreign_key_check')).all() == []
    print('Populated rollback/re-upgrade: PASS')
print('QA database:', scratch)
