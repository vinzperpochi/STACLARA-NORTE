#!/usr/bin/env python3
"""Interactively create a Barangay Official account and profile.

The configured database and all tables must already exist. Passwords are entered
with getpass, hashed by the User model, and never printed or stored in plain text.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from getpass import getpass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.extensions import db
from app.models import Official, Role, User
from run import ensure_runtime_schema


def create_official_user(
    username: str,
    email: str,
    password: str,
    full_name: str,
    position: str,
    term_start: date,
    contact_number: str | None = None,
    *, personnel_id: int | None = None,
) -> User:
    """Create an active user, official profile, and Barangay Official role."""
    username = username.strip()
    email = email.strip()
    full_name = full_name.strip()
    position = position.strip()
    contact_number = contact_number.strip() if contact_number else None

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
        db.select(Role).where(func.lower(Role.name) == "barangay official")
    )
    if role is None:
        role = Role(name="Barangay Official", description="Barangay official access")
        db.session.add(role)
        db.session.flush()

    official = Official(
        full_name=full_name,
        position=position,
        term_start=term_start,
        contact_number=contact_number,
        status="active",
    )
    db.session.add(official)
    db.session.flush()

    user = User(
        username=username,
        email=email,
        status="active",
        is_active=True,
        must_change_password=False,
        official_id=official.id,
    )
    user.set_password(password)
    user.roles.append(role)
    db.session.add(user)
    from app.attendance.accounts import provision_account_personnel
    provision_account_personnel(user, personnel_id=personnel_id)
    db.session.commit()
    return user


def main() -> int:
    print("Create a Barangay Official account and official profile")
    print("This command uses the configured database and does not create tables.")

    username = input("Official username (3-80 letters/numbers/._-): ").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", username):
        print("Hindi wasto ang username. Gumamit ng 3-80 letters, numbers, dot, underscore, o hyphen.", file=sys.stderr)
        return 2

    raw_email = input("Official email: ").strip()
    try:
        email = validate_email(raw_email, check_deliverability=False).normalized
    except EmailNotValidError as error:
        print(f"Hindi wasto ang email: {error}", file=sys.stderr)
        return 2

    full_name = input("Buong pangalan ng official: ").strip()
    position = input("Posisyon (hal. Kagawad, Barangay Captain): ").strip()
    if not full_name or len(full_name) > 200 or not position or len(position) > 100:
        print("Kailangan ang buong pangalan at posisyon; tingnan ang haba ng mga inilagay.", file=sys.stderr)
        return 2

    raw_term_start = input(f"Simula ng termino YYYY-MM-DD [default {date.today().isoformat()}]: ").strip()
    try:
        term_start = date.fromisoformat(raw_term_start) if raw_term_start else date.today()
    except ValueError:
        print("Hindi wasto ang petsa. Gamitin ang YYYY-MM-DD.", file=sys.stderr)
        return 2

    contact_number = input("Contact number (optional): ").strip() or None
    if contact_number and len(contact_number) > 30:
        print("Hanggang 30 characters lang ang contact number.", file=sys.stderr)
        return 2

    app = create_app("development")
    try:
        with app.app_context():
            ensure_runtime_schema()
            minimum = int(app.config.get("PASSWORD_MIN_LENGTH", 12))
            print("Paalala: nakatago ang pag-type ng password; walang lalabas na letra o asterisk. I-type ito at pindutin ang Enter.")
            while True:
                password = getpass(f"Official password (minimum {minimum} characters): ")
                if len(password) < minimum:
                    print(f"Masyadong maikli; gumamit ng hindi bababa sa {minimum} characters. Subukan ulit.")
                    continue
                confirmation = getpass("Ulitin ang password (nakatago rin): ")
                if password != confirmation:
                    print("Hindi magkatugma ang mga password. Subukan ulit.")
                    continue
                break

            print(
                f"\nAccount: {username} <{email}>\n"
                f"Official profile: {full_name} — {position}\n"
                f"Term start: {term_start.isoformat()}\nRole: Barangay Official"
            )
            if input("I-type ang CREATE para ituloy: ").strip() != "CREATE":
                print("Kinansela; walang account na ginawa.")
                return 1

            user = create_official_user(
                username, email, password, full_name, position, term_start, contact_number
            )
            print(f"Matagumpay na nagawa ang Barangay Official account para sa {user.email}.")
            print("Nasa database ang account, official profile, at role link; naka-hash ang password.")
            return 0
    except OperationalError as error:
        db.session.rollback()
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
        db.session.rollback()
        print(f"Hindi kumpleto ang database schema: {error}", file=sys.stderr)
        return 1
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        print(f"Hindi nagawa ang account: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        db.session.rollback()
        print(f"May error sa paglikha ng account: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
