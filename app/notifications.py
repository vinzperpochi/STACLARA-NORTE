"""Notify active barangay reviewers within the caller's transaction."""
from app.extensions import db
from app.models import Notification, Role, User


def notify_officials(title, message):
    reviewers = db.session.scalars(
        db.select(User).join(User.roles).where(
            Role.name.in_(['Barangay Official', 'System Administrator']),
            User.is_active.is_(True), User.status == 'active',
        ).distinct()
    ).all()
    for user in reviewers:
        db.session.add(Notification(user_id=user.id, title=title, message=message, status='active'))
