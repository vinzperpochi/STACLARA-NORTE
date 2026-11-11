"""Short-lived scanner reservations shared by web workers on the same host.

Only card digests are saved. Attendance and personnel remain in the main DB.
"""
import secrets
import sqlite3
import time
from contextlib import contextmanager, closing
from pathlib import Path
from flask import current_app


@contextmanager
def connection():
    path = Path(current_app.config.get('ATTENDANCE_CAPTURE_PATH', Path(current_app.config['STORAGE_ROOT']) / 'bridge' / 'registration.sqlite'))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS captures (id TEXT PRIMARY KEY, device_id INTEGER NOT NULL, actor_id INTEGER NOT NULL, state TEXT NOT NULL, expires REAL NOT NULL, ready REAL, digest TEXT, suffix TEXT, message TEXT)')
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM captures WHERE expires < ?', (time.time() - 600,))
        yield db


def begin(device_id, actor_id):
    with connection() as db:
        busy = db.execute("SELECT id FROM captures WHERE device_id=? AND state='waiting' AND expires>?", (device_id, time.time())).fetchone()
        if busy:
            raise ValueError('This reader is already waiting for a registration scan. Cancel that session or wait for it to expire.')
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO captures(id,device_id,actor_id,state,expires) VALUES(?,?,?,'waiting',?)", (token, device_id, actor_id, time.time()+60))
        return token


def get(token, actor_id):
    with connection() as db:
        row = db.execute('SELECT * FROM captures WHERE id=? AND actor_id=?', (token, actor_id)).fetchone()
        if not row:
            raise ValueError('Registration scan was not found. Scan the card again.')
        value = dict(row)
        if value['expires'] <= time.time():
            value['state'] = 'expired'
        value['ready'] = bool(value['ready'] and value['ready'] > time.time()-6)
        return value


def mode(device_id):
    with connection() as db:
        row = db.execute("SELECT id FROM captures WHERE device_id=? AND state='waiting' AND expires>?", (device_id, time.time())).fetchone()
        if not row:
            return None
        db.execute('UPDATE captures SET ready=? WHERE id=?', (time.time(), row['id']))
        return row['id']


def blocks_attendance(device_id, occurred_timestamp):
    """Guard live taps from an older bridge while the modal reserves this reader.

    Previously queued events predating the reservation remain attendance events.
    """
    with connection() as db:
        row = db.execute("SELECT expires FROM captures WHERE device_id=? AND state='waiting' AND expires>?", (device_id, time.time())).fetchone()
        return bool(row and occurred_timestamp >= row['expires']-60)


def receive(token, device_id, digest, suffix, duplicate=False):
    with connection() as db:
        row = db.execute('SELECT * FROM captures WHERE id=? AND device_id=?', (token, device_id)).fetchone()
        if not row or row['expires'] <= time.time() or row['state'] not in {'waiting', 'captured'}:
            raise ValueError('Registration was cancelled or expired. Open the scan modal again.')
        if row['state'] == 'captured':
            return
        if duplicate:
            db.execute('UPDATE captures SET message=? WHERE id=?', ('This card is already registered or revoked. Tap a different card.', token))
        else:
            db.execute("UPDATE captures SET state='captured',digest=?,suffix=?,expires=?,message=NULL WHERE id=?", (digest, suffix, time.time()+300, token))


def finish(token, actor_id, state='cancelled'):
    with connection() as db:
        if state == 'consumed':
            db.execute("UPDATE captures SET state=?,digest=NULL,message='audio_pending',expires=? WHERE id=? AND actor_id=?",
                       (state,time.time()+86400,token,actor_id))
        else:
            db.execute('UPDATE captures SET state=?,digest=NULL WHERE id=? AND actor_id=?', (state, token, actor_id))


def reader_feedback(device_id, token, acknowledge=False):
    """Only the owning reader may see/acknowledge the post-commit outcome."""
    if not isinstance(token,str) or not token or len(token)>128:
        raise ValueError('Invalid registration feedback token.')
    with connection() as db:
        row=db.execute('SELECT state,expires,message FROM captures WHERE id=? AND device_id=?',
                       (token,device_id)).fetchone()
        if not row:
            return {'capture_id':token,'state':'not_found','acknowledged':False}
        state=row['state'] if row['expires']>time.time() else 'expired'
        ack=row['message']=='audio_acknowledged'
        if acknowledge and state=='consumed':
            db.execute("UPDATE captures SET message='audio_acknowledged' WHERE id=? AND device_id=?",(token,device_id))
            ack=True
        return {'capture_id':token,'state':state,'acknowledged':ack}


def next_reader_feedback(device_id):
    with connection() as db:
        row=db.execute("SELECT id FROM captures WHERE device_id=? AND state='consumed' AND message='audio_pending' AND expires>? ORDER BY expires,id LIMIT 1",
                       (device_id,time.time())).fetchone()
        return {'capture_id':row['id'],'state':'consumed','acknowledged':False} if row else None
