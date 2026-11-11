"""Centralized audit logging helpers."""
from flask import request, has_request_context
from flask_login import current_user
from app.extensions import db
from app.models import AuditLog

def record(action: str, module: str, entity_type: str, entity_id: int | None = None, description: str | None = None):
    roles = ", ".join(sorted(role.name for role in getattr(current_user, "roles", []))) if current_user.is_authenticated else None
    db.session.add(AuditLog(user_id=current_user.id if current_user.is_authenticated else None, role=roles, action=action, module=module, entity_type=entity_type, entity_id=entity_id, description=description, details=description, ip_address=(request.remote_addr or None)))


# Administrative data changes and their audit rows share the same commit/rollback.
# Only identifiers and action names are recorded; no field values or passwords.
from sqlalchemy import event
from sqlalchemy.orm import Session


@event.listens_for(Session, 'after_flush')
def audit_entity_changes(session, flush_context):
    if not has_request_context() or not current_user.is_authenticated:
        return
    excluded = {'AuditLog', 'UserSession', 'LoginAttempt', 'Notification', 'Message'}
    explicit = {(log.entity_type, log.entity_id) for log in session.new if isinstance(log, AuditLog)}
    seen = session.info.setdefault('audited_entities', set())
    for action, objects in [('CREATE', session.new), ('UPDATE', session.dirty), ('DELETE', session.deleted)]:
        for obj in list(objects):
            name = type(obj).__name__
            key = (name, getattr(obj, 'id', None))
            if name in excluded or key in explicit or (action, key) in seen:
                continue
            if action == 'UPDATE' and not session.is_modified(obj, include_collections=True):
                continue
            seen.add((action, key))
            record(action, request.blueprint or 'system', name, key[1], 'Record change committed in the same transaction')


@event.listens_for(Session, 'after_transaction_end')
def reset_transaction_audit(session, transaction):
    if transaction.parent is None:
        session.info.pop('audited_entities', None)
