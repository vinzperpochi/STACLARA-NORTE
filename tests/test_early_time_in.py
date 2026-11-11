from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.attendance.service import MANILA, schedule_for, utc
from app.extensions import db
from app.models import AttendanceSession
from test_system_integrity import system
from test_attendance_operations import roster, scan_at


@pytest.mark.parametrize('seconds_before',[301,300,299,0,-420])
@pytest.mark.parametrize('flexible',[False,True])
def test_exact_five_minute_boundary_including_flexible_schedules(seconds_before,flexible):
    day=date(2026,11,5)
    schedule=SimpleNamespace(active=True,effective_from=day,effective_until=None,
        weekdays=[day.weekday()],start_time=time(8),end_time=time(17),flexible=flexible)
    stamp=datetime.combine(day,time(8),MANILA)-timedelta(seconds=seconds_before)
    person=SimpleNamespace(schedules=[schedule])
    if seconds_before>300:
        with pytest.raises(ValueError,match='Too early. Time In opens at 07:55 AM PHT.'):
            schedule_for(person,stamp.astimezone(timezone.utc))
    else:
        assert schedule_for(person,stamp.astimezone(timezone.utc))==(schedule,day)


@pytest.mark.parametrize('seconds_before',[301,300,0])
def test_reader_preview_and_final_scan_share_the_five_minute_rule(system,roster,monkeypatch,seconds_before):
    from app.attendance import routes
    person,schedule,_,headers,day=roster
    stamp=datetime.combine(day,time(8),MANILA)-timedelta(seconds=seconds_before)

    class ScanClock(datetime):
        @classmethod
        def now(cls,tz=None):
            return stamp.astimezone(tz) if tz else stamp.replace(tzinfo=None)

    monkeypatch.setattr(routes,'datetime',ScanClock)
    preview=system.test_client().post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'})
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    result=scan_at(system,roster,stamp,'early-in-boundary',action='IN')
    if seconds_before>300:
        assert preview.status_code==result.status_code==422
        assert preview.json['message']==result.json['message']=='Too early. Time In opens at 07:55 AM PHT.'
        assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    else:
        assert preview.status_code==result.status_code==200
        assert preview.json['action']==result.json['action']=='IN'
        session=db.session.scalar(db.select(AttendanceSession))
        assert utc(session.time_in)==stamp.astimezone(timezone.utc)
        assert session.work_date==day and session.late_minutes==0


@pytest.mark.parametrize('seconds_before',[301,300])
def test_midnight_shift_uses_next_duty_day_at_the_early_boundary(system,roster,seconds_before):
    person,schedule,_,_,day=roster
    work_day=day+timedelta(days=1)
    schedule.start_time=time(0,3);schedule.end_time=time(8)
    schedule.effective_from=work_day;schedule.weekdays=[work_day.weekday()]
    db.session.commit();db.session.expire(person,['schedules'])
    stamp=datetime.combine(work_day,time(0,3),MANILA)-timedelta(seconds=seconds_before)
    assert stamp.astimezone(MANILA).date()==day
    result=scan_at(system,roster,stamp,'midnight-early-in',action='IN')
    if seconds_before>300:
        assert result.status_code==422
        assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0
    else:
        assert result.status_code==200
        session=db.session.scalar(db.select(AttendanceSession))
        assert session.work_date==work_day
        assert utc(session.time_in)==stamp.astimezone(timezone.utc)


def test_evening_shift_opens_at_2155_and_not_2154():
    day=date(2026,11,5)
    schedule=SimpleNamespace(active=True,effective_from=day,effective_until=None,
        weekdays=[day.weekday()],start_time=time(22),end_time=time(6))
    person=SimpleNamespace(schedules=[schedule])
    with pytest.raises(ValueError,match='Too early'):
        schedule_for(person,datetime.combine(day,time(21,54),MANILA))
    assert schedule_for(person,datetime.combine(day,time(21,55),MANILA))==(schedule,day)
