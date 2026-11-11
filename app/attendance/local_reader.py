"""Opt-in, single-reader pairing for direct HTTP tests on a private LAN.

The chip ID is an identifier, not a secret. This transport is not production
authentication; credential-based HTTPS remains available outside this mode.
"""
import ipaddress
import re
import secrets
import time
from urllib.parse import urlsplit
from flask import abort, current_app, request
from app.extensions import db
from app.models import AttendanceDevice, AttendanceAuditLog
from .capture import connection

LAN = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))


def enabled():
    return bool(current_app.config.get('ATTENDANCE_LOCAL_TEST_MODE') and current_app.config.get('ATTENDANCE_LOCAL_TEST_ALLOWED'))


def private_address(value):
    try:
        address=ipaddress.ip_address(value)
        return address.is_loopback or any(address in network for network in LAN)
    except ValueError:
        return False


def init_store(store):
    store.execute('CREATE TABLE IF NOT EXISTS local_reader (id INTEGER PRIMARY KEY CHECK(id=1), device_id INTEGER NOT NULL, chip_id TEXT)')


def ensure(actor_id):
    """Called by an authenticated admin when opening the registration modal."""
    with connection() as store:
        init_store(store)
        saved=store.execute('SELECT device_id FROM local_reader WHERE id=1').fetchone()
        device=db.session.get(AttendanceDevice,saved['device_id']) if saved else None
        if device and not device.active:
            raise ValueError('The internal local reader is disabled. Contact the system administrator.')
        if device is None:
            device=AttendanceDevice(name='Local ESP32 RFID Reader',hardware='ESP32',credential_hash=secrets.token_hex(32),require_pin=False)
            db.session.add(device);db.session.flush()
            db.session.add(AttendanceAuditLog(actor_id=actor_id,device_id=device.id,entity_id=device.id,action='LOCAL_READER_CREATED',details='Single local testing reader created automatically'))
            db.session.commit()
            store.execute('INSERT OR REPLACE INTO local_reader(id,device_id,chip_id) VALUES(1,?,NULL)',(device.id,))
        return device


def authenticate():
    if not enabled(): abort(403,description='Local scanner testing is disabled.')
    try: host=urlsplit('http://'+request.host).hostname or ''
    except ValueError: abort(403)
    if not private_address(request.remote_addr or '') or not (host=='localhost' or private_address(host)):
        abort(403,description='Local scanner testing requires a direct private LAN address.')
    if any(request.headers.get(name) for name in ('Forwarded','X-Forwarded-For','X-Forwarded-Proto','X-Real-IP')):
        abort(403,description='Local scanner testing cannot be accessed through a proxy.')
    chip=request.headers.get('X-RFID-Reader','').upper()
    if not re.fullmatch(r'[0-9A-F]{12}',chip): abort(400,description='Missing ESP32 chip identifier.')
    with connection() as store:
        init_store(store)
        saved=store.execute('SELECT * FROM local_reader WHERE id=1').fetchone()
        if not saved: abort(409,description='Open Scan RFID Card/Tag once to pair the reader.')
        device=db.session.get(AttendanceDevice,saved['device_id'])
        if not device or not device.active: abort(403,description='Local reader is unavailable.')
        if saved['chip_id'] and saved['chip_id']!=chip:
            abort(403,description='A different ESP32 is already paired.')
        if not saved['chip_id']:
            waiting=store.execute("SELECT id FROM captures WHERE device_id=? AND state='waiting' AND expires>?",(device.id,time.time())).fetchone()
            if not waiting: abort(409,description='Open Scan RFID Card/Tag once to pair the reader.')
            store.execute('UPDATE local_reader SET chip_id=? WHERE id=1',(chip,))
            db.session.add(AttendanceAuditLog(device_id=device.id,entity_id=device.id,action='LOCAL_READER_PAIRED',details='ESP32 identifier paired during an administrator registration session'))
            db.session.commit()
        return device
