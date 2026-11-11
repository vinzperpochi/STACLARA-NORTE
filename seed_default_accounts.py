#!/usr/bin/env python3
"""Optional development account seeder; requires a manually provisioned schema."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone

from flask import current_app

from app import create_app
from app.extensions import db
from app.models import Role, User

DEFAULT_ACCOUNTS = [
    {
        "username": "admin",
        "email": "admin@barangay.gov",
        "password": "Admin@123456",
        # Super Admin and Barangay Official are separate workspaces.
        "roles": ["System Administrator"],
    },
    {
        "username": "official",
        "email": "official@barangay.gov",
        "password": "Official@123456",
        "roles": ["Barangay Official"],
    },
]


def get_or_create_role(name: str, description: str) -> Role:
    role = db.session.scalar(db.select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.flush()
    return role


def ensure_default_accounts() -> dict[str, str]:
    try:
        app = current_app._get_current_object()
        context = nullcontext()
    except RuntimeError:
        app = create_app("development")
        context = app.app_context()

    with context:
        if not app.testing and not app.config.get("ALLOW_DEVELOPMENT_SEED", False):
            raise RuntimeError("Default account seeding is restricted to development and testing.")
        get_or_create_role("Resident", "Registered barangay resident")
        get_or_create_role("System Administrator", "Full system access")
        get_or_create_role("Barangay Official", "Official access")

        created = {}

        for account in DEFAULT_ACCOUNTS:
            user = db.session.scalar(
                db.select(User).where(
                    (User.username == account["username"]) | (User.email == account["email"])
                )
            )

            if user is None:
                user = User(
                    username=account["username"],
                    email=account["email"],
                    status="active",
                    is_active=True,
                    privacy_consent_at=datetime.now(timezone.utc),
                    privacy_consent_version=app.config["PRIVACY_NOTICE_VERSION"],
                )
                db.session.add(user)

            user.username = account["username"]
            user.email = account["email"]
            user.status = "active"
            user.is_active = True
            user.privacy_consent_at = user.privacy_consent_at or datetime.now(timezone.utc)
            user.privacy_consent_version = user.privacy_consent_version or app.config["PRIVACY_NOTICE_VERSION"]
            user.set_password(account["password"])
            db.session.flush()

            user.roles = []
            for role_name in account["roles"]:
                role = get_or_create_role(role_name, role_name)
                if role not in user.roles:
                    user.roles.append(role)

            created[account["username"]] = account["password"]

        db.session.commit()
        return created


if __name__ == "__main__":
    seeded = ensure_default_accounts()
    print("Default accounts seeded:")
    for username, password in seeded.items():
        print(f"- {username}: {password}")
