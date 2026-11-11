"""Daily records show actual Philippine times for every recorded session."""
from datetime import datetime, time, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
import pytest
from app.extensions import db
from app.models import AttendanceSession
from app.attendance.service import MANILA
from test_system_integrity import system, login
from test_attendance_operations import roster, scan_at


def at(day,hour,minute=0):
    return datetime.combine(day,time(hour,minute),MANILA).astimezone(timezone.utc)


def daily_table(response):
    assert response.status_code==200
    html=response.get_data(as_text=True)
    return html.split('<table class="civic-table ops-table ops-daily-records">',1)[1].split('</table>',1)[0]


def test_daily_times_include_all_sessions_and_an_open_timeout(system,roster):
    person,schedule,_,_,day=roster
    db.session.add_all([
        AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,work_date=day,time_in=at(day,8,5),time_out=at(day,12,15)),
        AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,work_date=day,time_in=at(day,13,10))
    ]);db.session.commit()
    admin=login(system,'admin-test')
    html=daily_table(admin.get('/attendance/?date='+str(day)))
    for value in ['<th>Time In</th>','<th>Time Out</th>','08:05 AM','12:15 PM','01:10 PM','Not yet','Session #2']:
        assert value in html
    own=daily_table(login(system,'staff-test').get('/attendance/?date='+str(day)))
    assert '08:05 AM' in own and '12:15 PM' in own


def test_overnight_timeout_shows_next_day_and_missing_records_show_dashes(system,roster):
    person,schedule,_,_,day=roster
    schedule.start_time=time(22);schedule.end_time=time(6)
    next_day=day+timedelta(days=1)
    db.session.add(AttendanceSession(personnel_id=person.id,schedule_id=schedule.id,work_date=day,time_in=at(day,22),time_out=at(next_day,6,30)))
    db.session.commit();admin=login(system,'admin-test')
    html=daily_table(admin.get('/attendance/?date='+str(day)))
    assert '10:00 PM' in html and '06:30 AM' in html and next_day.strftime('%b %d') in html
    missing=daily_table(admin.get('/attendance/?date='+str(day-timedelta(days=1))))
    assert missing.count('—')>=2 and '12:00 AM' not in missing
    empty=daily_table(admin.get('/attendance/?q=no-matching-person'))
    assert 'colspan="8"' in empty  # Admin rows include personnel actions.
    own_empty=daily_table(login(system,'staff-test').get('/attendance/?q=no-matching-person'))
    assert 'colspan="7"' in own_empty


@pytest.mark.parametrize('username',['admin-test','staff-test'])
def test_0807_scan_has_timezone_aware_metadata_and_local_edit_values(system,roster,username):
    assert scan_at(system,roster,at(roster[4],8,7),'clock0807',action='IN').status_code==200
    assert scan_at(system,roster,at(roster[4],8,8),'clock0808',action='OUT').status_code==200
    response=login(system,username).get('/attendance/?date='+str(roster[4]))
    assert response.status_code==200

    class Times(HTMLParser):
        def __init__(self):
            super().__init__();self.times=[];self.edits={}

        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='time' and attrs.get('data-fmt')=='time': self.times.append(attrs)
            if tag=='input' and attrs.get('type')=='datetime-local': self.edits[attrs['name']]=attrs['value']

    html=response.get_data(as_text=True)
    parser=Times();parser.feed(html)
    assert len(parser.times)==2
    for attrs,minute in zip(parser.times,[7,8]):
        instant=datetime.fromisoformat(attrs['datetime'])
        assert instant.tzinfo is not None
        assert instant==at(roster[4],8,minute)
        assert instant.astimezone(MANILA).hour==8
    assert '08:07 AM' in html and '08:08 AM' in html
    if username=='admin-test':
        assert parser.edits['time_in']==str(roster[4])+'T08:07'
        assert parser.edits['time_out']==str(roster[4])+'T08:08'
    # Actual rendered pages for the browser regression, using isolated test data.
    output=Path(__file__).resolve().parents[1]/'.test-storage'/'attendance-time-regression'
    output.mkdir(parents=True,exist_ok=True)
    (output/(username+'.html')).write_text(html,encoding='utf-8')


def test_machine_timestamp_filter_normalizes_naive_utc_and_aware_values(system):
    iso=system.jinja_env.filters['datetime_utc_iso']
    expected='2026-11-05T00:07:00+00:00'
    assert iso(datetime(2026,11,5,0,7))==expected
    assert iso(datetime(2026,11,5,0,7,tzinfo=timezone.utc))==expected
    assert iso(datetime(2026,11,5,8,7,tzinfo=MANILA))==expected
