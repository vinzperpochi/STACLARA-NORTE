"""Configurable retention review without deleting evidence or audit history."""
from datetime import datetime, timedelta, timezone
import click
from sqlalchemy import select, func
from app.extensions import db
from app.models import AttendanceLog, ResidentComplaint


def register_retention_command(app):
    @app.cli.command('operations-retention-review')
    def retention_review():
        now=datetime.now(timezone.utc)
        attendance_cutoff=now-timedelta(days=app.config['ATTENDANCE_RETENTION_DAYS'])
        incident_cutoff=now-timedelta(days=app.config['INCIDENT_RETENTION_DAYS'])
        attendance=db.session.scalar(select(func.count(AttendanceLog.id)).where(AttendanceLog.created_at<attendance_cutoff))
        incidents=db.session.scalar(select(func.count(ResidentComplaint.id)).where(ResidentComplaint.created_at<incident_cutoff,ResidentComplaint.status=='CLOSED'))
        click.echo(f'Retention review: {attendance} old attendance events; {incidents} old closed incidents. No records deleted.')
        click.echo('Review office retention policy, legal holds and backups before any separate archive or disposal action.')
