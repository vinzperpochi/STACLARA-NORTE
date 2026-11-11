"""Apply the frozen migration to an old-schema database and preserve an existing row."""
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
import importlib.util
from app.extensions import db
from test_system_integrity import system


def test_add_only_operations_migration_preserves_existing_data(system):
    engine=create_engine('sqlite://')
    names={'personnel_profiles','rfid_cards','attendance_devices','attendance_logs','attendance_sessions','employee_schedules','attendance_adjustments','employee_leaves','attendance_audit_logs','resident_complaints','incident_categories','emergency_incidents','government_agencies','agency_hotlines','hotline_verifications','incident_routing_rules','complaint_assignments','complaint_referrals','complaint_status_history','complaint_evidence','complaint_notifications','complaint_audit_logs'}
    db.metadata.create_all(engine,tables=[t for name,t in db.metadata.tables.items() if name not in names])
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO roles(name,status) VALUES ('preserved-existing-role','active')"))
        previous=set(inspect(connection).get_table_names())
        path=Path(__file__).resolve().parents[1]/'migrations/versions/d7a91e8b420c_attendance_incidents.py'
        spec=importlib.util.spec_from_file_location('operations_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
        assert set(inspect(connection).get_table_names())==previous|names
        assert connection.execute(text("SELECT name FROM roles")).scalar_one()=='preserved-existing-role'
        for table in names-{'government_agencies','incident_categories','attendance_devices'}: assert inspect(connection).get_foreign_keys(table)
    engine.dispose()
