"""The direct-registration migration preserves existing data and links."""
import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_direct_registration_migration_preserves_existing_personnel():
    path=Path(__file__).resolve().parents[1]/'migrations/versions/e8b2f901d6aa_allow_unlinked_rfid_personnel.py'
    spec=importlib.util.spec_from_file_location('rfid_personnel_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE users(id INTEGER PRIMARY KEY)'))
        conn.execute(sa.text('INSERT INTO users VALUES(1)'))
        conn.execute(sa.text('CREATE TABLE personnel_profiles(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id), photo_filename VARCHAR(255) NOT NULL, department VARCHAR(100) NOT NULL, mobile VARCHAR(30) NOT NULL, email VARCHAR(255) NOT NULL, employment_status VARCHAR(40) NOT NULL)'))
        conn.execute(sa.text("INSERT INTO personnel_profiles VALUES(1,1,'photo.png','Office','09123456789','test@example.com','Regular')"))
        before=conn.execute(sa.text('SELECT * FROM personnel_profiles')).all()
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            assert all(col['nullable'] for col in sa.inspect(conn).get_columns('personnel_profiles') if col['name']!='id')
            assert conn.execute(sa.text('SELECT * FROM personnel_profiles')).all()==before
            conn.execute(sa.text('INSERT INTO personnel_profiles(id) VALUES(2)'))
            with pytest.raises(RuntimeError,match='Link personnel'):
                migration.downgrade()
    engine.dispose()
