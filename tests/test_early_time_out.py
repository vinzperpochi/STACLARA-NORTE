from datetime import datetime,time,timedelta
import pytest
from app.extensions import db
from app.models import AttendanceSession,AttendanceLog
from app.attendance.service import MANILA,session_metrics,daily_rows
from test_system_integrity import system,login
from test_attendance_operations import roster,scan_at


@pytest.mark.parametrize('action',['AUTO','OUT'])
def test_early_out_is_accepted_even_below_short_session_threshold(system,roster,action):
    person,schedule,_,_,day=roster
    schedule.minimum_session_minutes=480;db.session.commit()
    start=datetime.combine(day,time(8),MANILA)
    assert scan_at(system,roster,start,'early-in-001').status_code==200
    end=start+timedelta(minutes=1)
    result=scan_at(system,roster,end,'early-out-001',action=action)
    assert result.status_code==200 and result.json['action']=='OUT'
    assert 'Early Time Out recorded' in result.json['message']
    session=db.session.scalar(db.select(AttendanceSession))
    metrics=session_metrics(session)
    assert metrics['worked_minutes']==1 and metrics['early_minutes']==539 and metrics['short_session']
    row=daily_rows(day,[person])[0]
    assert row['early_minutes']==539 and row['undertime_minutes']==539
    page=login(system,'admin-test').get('/attendance/?date='+str(day)).get_data(as_text=True)
    assert '08:01 AM' in page and 'Early out' in page and '539 minutes before scheduled shift end' in page
    replay=scan_at(system,roster,end,'early-out-001',action=action)
    assert replay.json['replayed']
    assert db.session.scalar(db.select(db.func.count(AttendanceLog.id)))==2


def test_early_out_retains_rapid_repeat_protection(system,roster):
    start=datetime.combine(roster[4],time(8),MANILA)
    assert scan_at(system,roster,start,'guarded-in').status_code==200
    response=scan_at(system,roster,start+timedelta(seconds=10),'guarded-out',action='OUT')
    assert response.status_code==422 and 'Wait 30 seconds' in response.json['message']
    session=db.session.scalar(db.select(AttendanceSession));assert session.time_out is None


def test_regular_timeout_is_not_labelled_early(system,roster):
    start=datetime.combine(roster[4],time(8),MANILA)
    scan_at(system,roster,start,'normal-in')
    response=scan_at(system,roster,start+timedelta(hours=9),'normal-out',action='OUT')
    assert response.status_code==200 and response.json['message']=='Time Out recorded'
    assert session_metrics(db.session.scalar(db.select(AttendanceSession)))['early_minutes']==0
