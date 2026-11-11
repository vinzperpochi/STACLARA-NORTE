from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.attendance.service import MANILA, schedule_for
from app.extensions import db
from app.models import AttendanceSession
from test_system_integrity import system, login
from test_attendance_operations import roster


DAY = date(2026, 11, 5)  # Thursday, Philippine time.
SCAN = datetime.combine(DAY, time(1, 17), MANILA)


def shift(**changes):
    values = dict(active=True, effective_from=DAY, effective_until=None,
                  weekdays=[0, 1, 2, 4], start_time=time(1, 3), end_time=time(5))
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize('schedules,message', [
    ([], 'No active work schedule assigned.'),
    ([shift(active=False)], 'No active work schedule assigned.'),
    ([shift()], 'Not a scheduled work day: Thu Nov 05, 2026 PHT.'),
    ([shift(effective_from=DAY+timedelta(days=1))], 'No effective schedule for Thu Nov 05, 2026 PHT.'),
    ([shift(effective_until=DAY-timedelta(days=2))], 'No effective schedule for Thu Nov 05, 2026 PHT.'),
    ([shift(weekdays=[3], start_time=time(8), end_time=time(17))], 'Too early. Time In opens at 07:55 AM PHT.'),
])
def test_schedule_rejection_explains_the_failed_condition(schedules, message):
    with pytest.raises(ValueError) as error:
        schedule_for(SimpleNamespace(schedules=schedules), SCAN.astimezone(timezone.utc))
    assert str(error.value) == message
    assert len(message) <= 63  # Fits the firmware's existing three error lines.


def test_thursday_is_accepted_when_selected_and_overnight_keeps_start_day():
    schedule=shift(weekdays=[3])
    assert schedule_for(SimpleNamespace(schedules=[schedule]), SCAN) == (schedule, DAY)
    night=shift(effective_from=DAY-timedelta(days=1), weekdays=[2], start_time=time(22), end_time=time(6))
    assert schedule_for(SimpleNamespace(schedules=[night]), SCAN) == (night, DAY-timedelta(days=1))


def test_preview_explains_thursday_rejection_and_accepts_corrected_work_day(system, roster, monkeypatch):
    from app.attendance import routes

    class ScanClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return SCAN.astimezone(tz) if tz else SCAN.replace(tzinfo=None)

    monkeypatch.setattr(routes, 'datetime', ScanClock)
    person,schedule,_,headers,_=roster
    schedule.start_time=time(1,3);schedule.end_time=time(5)
    schedule.effective_from=DAY;schedule.weekdays=[0,1,2,4]
    db.session.commit()
    client=system.test_client()
    result=client.post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'})
    assert result.status_code==422
    assert result.json['message']=='Not a scheduled work day: Thu Nov 05, 2026 PHT.'
    assert result.json['employee']==person.full_name
    schedule.weekdays=[0,1,2,3,4];db.session.commit()
    result=client.post('/attendance/api/preview',headers=headers,json={'uid':'AABBCCDD'})
    assert result.status_code==200 and result.json['action']=='IN'
    assert db.session.scalar(db.select(db.func.count(AttendanceSession.id)))==0


def test_manage_record_displays_saved_work_days(system, roster):
    person,schedule,_,_,_=roster
    schedule.weekdays=[0,1,2,4];db.session.commit()
    page=login(system,'admin-test').get(f'/attendance/personnel/{person.id}')
    assert page.status_code==200
    assert b'Work days:</strong> Mon, Tue, Wed, Fri' in page.data
    assert b'Philippine Standard Time (PHT)' in page.data
