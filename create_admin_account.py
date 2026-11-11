#!/usr/bin/env python3
"""Interactively create a real administrator account in the configured database.

The database and all tables must already exist. Passwords are entered with getpass,
hashed through the User model, and are never printed or written in plain text.
"""
from __future__ import annotations

import re
import sys
from getpass import getpass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.extensions import db
from app.models import Role, User
from run import ensure_runtime_schema


def create_admin_user(username: str, email: str, password: str, *, personnel_id: int | None = None) -> User:
    """Create an active System Administrator account; never creates tables."""
    username = username.strip()
    email = email.strip()

    existing = db.session.scalar(
        db.select(User).where(
            or_(
                func.lower(User.username) == username.lower(),
                func.lower(User.email) == email.lower(),
            )
        )
    )
    if existing is not None:
        raise ValueError("May account na gamit ang username o email na iyon; pumili ng iba.")

    role = db.session.scalar(
        db.select(Role).where(func.lower(Role.name) == "system administrator")
    )
    if role is None:
        role = Role(name="System Administrator", description="Full system access")
        db.session.add(role)
        db.session.flush()

    user = User(
        username=username,
        email=email,
        status="active",
        is_active=True,
        must_change_password=True,
    )
    user.set_password(password)
    user.roles.append(role)
    db.session.add(user)
    from app.attendance.accounts import provision_account_personnel
    provision_account_personnel(user, personnel_id=personnel_id)
    db.session.commit()
    return user


def main() -> int:
    print("Create a System Administrator account")
    print("This command uses the configured database and does not create tables.")

    username = input("Admin username (3-80 letters/numbers/._-): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", username):
        print("Hindi wasto ang username. Gumamit ng 3-80 letters, numbers, dot, underscore, o hyphen.", file=sys.stderr)
        return 2

    raw_email = input("Admin email: ").strip()
    try:
        email = validate_email(raw_email, check_deliverability=False).normalized
    except EmailNotValidError as error:
        print(f"Hindi wasto ang email: {error}", file=sys.stderr)
        return 2

    app = create_app("development")
    try:
        with app.app_context():
            ensure_runtime_schema()
            minimum = int(app.config.get("PASSWORD_MIN_LENGTH", 12))
            print("Paalala: nakatago ang pag-type ng password; walang lalabas na letra o asterisk. I-type ito at pindutin ang Enter.")
            while True:
                password = getpass(f"Admin password (minimum {minimum} characters): ")
                if len(password) < minimum:
                    print(f"Masyadong maikli; gumamit ng hindi bababa sa {minimum} characters. Subukan ulit.")
                    continue
                confirmation = getpass("Ulitin ang password (nakatago rin): ")
                if password != confirmation:
                    print("Hindi magkatugma ang mga password. Subukan ulit.")
                    continue
                break

            print(f"\nAccount: {username} <{email}>\nRole: System Administrator")
            if input("I-type ang CREATE para ituloy: ").strip() != "CREATE":
                print("Kinansela; walang account na ginawa.")
                return 1

            user = create_admin_user(username, email, password)
            print(f"Matagumpay na nagawa ang admin account para sa {user.email}.")
            print("Kailangan mong palitan ang pansamantalang password sa unang pag-login.")
            print("Hindi ipinakita o ini-save ng script ang password sa plain text.")
            return 0
    except OperationalError as error:
        original = getattr(error, "orig", error)
        args = getattr(original, "args", ())
        if args and args[0] == 1049:
            print(
                "Hindi makita ang database na 'staclaranorte'. Gumawa muna nito sa phpMyAdmin, "
                "i-import ang database/mysql_schema.sql, at tiyaking DB_NAME=staclaranorte sa .env.",
                file=sys.stderr,
            )
        else:
            print(f"Hindi makakonekta sa database: {original}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"Hindi kumpleto ang database schema: {error}", file=sys.stderr)
        return 1
    except (ValueError, IntegrityError) as error:
        print(f"Hindi nagawa ang account: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"May error sa paglikha ng account: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
