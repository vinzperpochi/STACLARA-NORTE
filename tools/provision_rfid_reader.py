"""Issue a device credential from an authorized production terminal."""

from argparse import ArgumentParser
from hashlib import sha256
import secrets

from sqlalchemy import select, text

from app import create_app
from app.extensions import db
from app.models import AttendanceAuditLog, AttendanceDevice


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--rotate-reader", type=int, help="Replace the credential for this active reader ID.")
    args = parser.parse_args()
    with create_app("production").app_context():
        if db.engine.dialect.name != "postgresql":
            parser.error("Use the deployment's PostgreSQL connection.")
        db.session.execute(text("SELECT pg_advisory_xact_lock(84652124)"))
        active = db.session.scalars(
            select(AttendanceDevice).where(AttendanceDevice.active.is_(True)).with_for_update()
        ).all()
        if args.rotate_reader is not None:
            if len(active) != 1 or active[0].id != args.rotate_reader:
                parser.error("Rotation requires the ID of the sole active reader.")
            device = active[0]
            if device.require_pin or device.hardware == "Development test only":
                parser.error("This reader configuration is incompatible with the ESP32 firmware.")
            action = "PUBLIC_READER_CREDENTIAL_ROTATED"
        else:
            if active:
                ids = ", ".join(str(device.id) for device in active)
                parser.error(f"Active reader IDs: {ids}. Review them before using --rotate-reader.")
            device = AttendanceDevice(name="Public ESP32 RFID Reader", hardware="ESP32")
            db.session.add(device)
            action = "PUBLIC_READER_CREATED"
        secret = secrets.token_urlsafe(32)
        device.credential_hash = sha256(secret.encode()).hexdigest()
        db.session.flush()
        device_id = device.id
        db.session.add(AttendanceAuditLog(
            device_id=device_id, entity_id=device_id, action=action,
            details="Issued through the authorized terminal",
        ))
        db.session.commit()
        print(f"{device_id}:{secret}")


if __name__ == "__main__":
    main()
