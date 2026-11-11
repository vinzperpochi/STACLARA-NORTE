import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration_module():
    path=Path(__file__).resolve().parents[1]/'migrations/versions/f2a914c8b031_one_active_rfid_per_personnel.py'
    spec=importlib.util.spec_from_file_location('one_active_rfid_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_unique_migration_preserves_assignments_and_allows_revoked_history():
    engine=sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE rfid_cards(id INTEGER PRIMARY KEY,personnel_id INTEGER NOT NULL,uid_hash TEXT NOT NULL UNIQUE,active BOOLEAN NOT NULL)'))
        connection.execute(sa.text("INSERT INTO rfid_cards VALUES(1,1,'first',true),(2,2,'second',true)"))
        before=connection.execute(sa.text('SELECT * FROM rfid_cards')).all()
        with Operations.context(MigrationContext.configure(connection)):
            migration_module().upgrade()
        assert connection.execute(sa.text('SELECT * FROM rfid_cards')).all()==before
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("INSERT INTO rfid_cards VALUES(3,1,'third',true)"))
        connection.execute(sa.text('UPDATE rfid_cards SET active=false WHERE id=1'))
        connection.execute(sa.text("INSERT INTO rfid_cards VALUES(3,1,'third',true)"))
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(sa.text("INSERT INTO rfid_cards VALUES(4,2,'first',false)"))
        assert connection.execute(sa.text('SELECT personnel_id FROM rfid_cards WHERE id=1')).scalar()==1
    engine.dispose()


def test_unique_migration_refuses_to_choose_between_existing_duplicate_cards():
    engine=sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE rfid_cards(id INTEGER PRIMARY KEY,personnel_id INTEGER NOT NULL,active BOOLEAN NOT NULL)'))
        connection.execute(sa.text('INSERT INTO rfid_cards VALUES(1,1,true),(2,1,true)'))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError,match='Multiple active RFID'):
                migration_module().upgrade()
        assert connection.execute(sa.text('SELECT count(*) FROM rfid_cards WHERE active=true')).scalar()==2
    engine.dispose()
