"""Offline queue and reconnect behavior with real Flask scan decisions, no hardware claim."""
import importlib.util
from pathlib import Path
from urllib.error import URLError
from app.extensions import db
from app.models import AttendanceSession
from test_system_integrity import system
from test_attendance_operations import roster


def bridge():
    path=Path(__file__).resolve().parents[1]/'hardware/serial_bridge.py'
    spec=importlib.util.spec_from_file_location('test_bridge',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_disconnect_retains_event_reconnect_delivers_once(system,roster,monkeypatch):
    from datetime import datetime, time
    from app.attendance.service import MANILA
    module=bridge();queue=module.queue_open(Path(system.config['STORAGE_ROOT'])/'test-queue.sqlite')
    event=module.enqueue(queue,'AABBCCDD')
    from json import dumps
    event['occurred_at']=datetime.combine(roster[4],time(8),MANILA).isoformat();queue.execute('UPDATE queue SET body=?',(dumps(event),));queue.commit()
    def disconnected(*args): raise URLError('Disconnected')
    monkeypatch.setattr(module,'deliver',disconnected)
    module.send_pending(queue,'http://127.0.0.1:5002','test')
    assert queue.execute('SELECT count(*) FROM queue WHERE state="pending"').fetchone()[0]==1
    def deliver(server,credential,event):
        response=system.test_client().post('/attendance/api/scan',json=event,headers=roster[3]);return response.status_code,response.json
    monkeypatch.setattr(module,'deliver',deliver)
    module.send_pending(queue,'http://127.0.0.1:5002','test')
    module.send_pending(queue,'http://127.0.0.1:5002','test')
    assert queue.execute('SELECT count(*) FROM queue').fetchone()[0]==0
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==1
    queue.close()


def test_pin_not_persisted_and_terminal_rejections_do_not_retry(system,monkeypatch):
    module=bridge();queue=module.queue_open(Path(system.config['STORAGE_ROOT'])/'reject-queue.sqlite')
    module.enqueue(queue,'11223344',pin='123456')
    assert '123456' not in queue.execute('SELECT body FROM queue').fetchone()[0]
    calls=[]
    def reject(*args): calls.append(True);return 422,{'success':False,'message':'Unknown RFID card'}
    monkeypatch.setattr(module,'deliver',reject)
    module.send_pending(queue,'http://127.0.0.1:5002','test');module.send_pending(queue,'http://127.0.0.1:5002','test')
    assert len(calls)==1 and queue.execute('SELECT state,body FROM queue').fetchone()==('rejected','{}')
    queue.close()
