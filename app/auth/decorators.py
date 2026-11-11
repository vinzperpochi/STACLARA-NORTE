"""Authorization decorators for authenticated application areas."""

from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required


def roles_required(*role_names: str):
    """Require authentication and at least one named role."""

    required = {name.casefold() for name in role_names}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user_roles = {role.name.casefold() for role in current_user.roles if role.status == 'active'}
            if not required.intersection(user_roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def resident_owner_required(view):
    """Require a resident account linked to the authenticated user."""

    @wraps(view)
    @roles_required("Resident")
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            # This should be handled by @login_required in roles_required
            return redirect(url_for("auth.login"))
        
        if not hasattr(current_user, 'resident') or current_user.resident is None:
            flash("Access denied. Resident account required. Please contact administrator.", "danger")
            return redirect(url_for("main.index"))
        
        return view(*args, **kwargs)

    return wrapped


def official_account_required(view):
    """Allow both barangay officials and system administrators to access official features."""

    @wraps(view)
    @roles_required("Barangay Official", "System Administrator")
    def wrapped(*args, **kwargs):
        return view(*args, **kwargs)

    return wrapped
