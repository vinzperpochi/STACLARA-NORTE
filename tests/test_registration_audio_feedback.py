"""Speech success is tied to committed registration, scoped and acknowledged by reader."""
from unittest.mock import patch
from datetime import datetime,timezone
from app.attendance import capture
from app.extensions import db
from app.models import AttendanceDevice,RFIDCard
from test_system_integrity import system,login
from test_attendance_operations import roster
from test_rfid_registration import start,FIRST_SCHEDULE


def poll(system,headers,**body):
    return system.test_client().post('/attendance/api/registration-mode',headers=headers,json=body)


def form(token,**changes):
    values={**FIRST_SCHEDULE,'action':'register_card','capture_id':token,'first_name':'Voice','last_name':'Test',
        'barangay_role':'Barangay Staff','employee_id':'VOICE-001'}
    values.update(changes);return values


def test_only_saved_registration_produces_repeatable_feedback_until_acknowledged(system,roster):
    admin=login(system,'admin-test');device=roster[2];headers=roster[3]
    token=start(admin,device)
    assert poll(system,headers).json['registration_feedback'] is None
    assert system.test_client().post('/attendance/api/registration-tap',headers=headers,json={'capture_id':token,'uid':'11223344'}).status_code==200
    assert poll(system,headers).json['registration_feedback'] is None
    assert admin.post('/attendance/devices',data=form(token,end_time='08:00')).status_code==200
    assert poll(system,headers).json['registration_feedback'] is None
    assert admin.post('/attendance/devices',data=form(token)).status_code==302
    for _ in range(2):
        feedback=poll(system,headers).json['registration_feedback']
        assert feedback['capture_id']==token and feedback['state']=='consumed' and not feedback['acknowledged']
    response=poll(system,headers,ack_capture_id=token)
    assert response.json['feedback_acknowledged']==token and response.json['registration_feedback'] is None
    assert poll(system,headers,ack_capture_id=token).json['feedback_acknowledged']==token
    assert poll(system,headers).json['registration_feedback'] is None


def test_cancel_expiry_and_wrong_reader_cannot_announce_success(system,roster):
    admin=login(system,'admin-test');token=start(admin,roster[2]);headers=roster[3]
    admin.post('/attendance/registration/'+token+'/cancel')
    assert poll(system,headers).json['registration_feedback'] is None
    assert poll(system,headers,ack_capture_id=token).json['feedback_acknowledged'] is None
    with capture.connection() as conn:
        conn.execute("UPDATE captures SET state='consumed',message='audio_pending',expires=? WHERE id=?",(datetime.now(timezone.utc).timestamp()+3600,token))
    assert capture.next_reader_feedback(roster[2].id+999) is None
    assert capture.reader_feedback(roster[2].id+999,token,True)['state']=='not_found'
    with capture.connection() as conn:conn.execute('UPDATE captures SET expires=0 WHERE id=?',(token,))
    assert poll(system,headers).json['registration_feedback'] is None


def test_unauthorized_and_malformed_feedback_requests_are_rejected(system,roster):
    assert poll(system,{}).status_code==401
    assert poll(system,roster[3],ack_capture_id={'bad':'token'}).status_code==400
    assert system.test_client().post('/attendance/api/registration-mode',headers=roster[3],json=[]).status_code==400


def test_database_failure_does_not_publish_registered_audio(system,roster):
    admin=login(system,'admin-test');token=start(admin,roster[2]);headers=roster[3]
    system.test_client().post('/attendance/api/registration-tap',headers=headers,json={'capture_id':token,'uid':'11223344'})
    with patch.object(db.session,'commit',side_effect=RuntimeError('Synthetic DB failure')):
        try:admin.post('/attendance/devices',data=form(token))
        except RuntimeError:pass
    assert capture.next_reader_feedback(roster[2].id) is None
    assert not db.session.scalar(db.select(RFIDCard).where(RFIDCard.uid_suffix=='3344'))
