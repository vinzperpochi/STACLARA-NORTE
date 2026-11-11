"""Central permissions for the existing three account roles."""
from functools import wraps
from flask import abort
from flask_login import current_user, login_required

PERMISSIONS = {
    'System Administrator': {'dashboard', 'residents.manage', 'puroks.manage', 'puroks.view', 'blotters.manage', 'users.manage', 'settings.manage', 'reports.view', 'documents.review', 'workspace'},
    'Barangay Official': {'dashboard', 'residents.manage', 'puroks.view', 'blotters.manage', 'reports.view', 'documents.review', 'workspace'},
    'Resident': {'dashboard', 'profile.own', 'documents.own', 'blotters.own', 'workspace'},
}


def can(permission):
    if not current_user.is_authenticated: return False
    from app.extensions import db
    from app.models import SystemSetting
    for role in current_user.roles:
        if role.status != 'active': continue
        if role.name == 'System Administrator': return True
        override=db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key==f'role_permissions_override_{role.id}'))
        configured={(p.resource if p.action=='access' else f'{p.resource}.{p.action}') for p in role.permissions}
        allowed=configured if override and override.setting_value=='yes' else configured | PERMISSIONS.get(role.name,set())
        # Resident roles cannot acquire management capabilities through a mistaken assignment.
        if role.name=='Resident': allowed &= PERMISSIONS['Resident']
        if permission in allowed: return True
    return False


def permission_required(permission):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not can(permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate
