"""Growing attendance lists keep totals, exports and account boundaries intact."""
import csv
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import template_rendered

from app.extensions import db
from app.models import AttendanceLog, AttendanceSession, EmployeeLeave, EmployeeSchedule, PersonnelProfile, RFIDCard
from test_system_integrity import system, login
from test_attendance_operations import roster, scan_at


@contextmanager
def rendered(app):
    contexts = []
    def record(sender, template, context, **extra):
        contexts.append(context)
    template_rendered.connect(record, app)
    try:
        yield contexts
    finally:
        template_rendered.disconnect(record, app)


@pytest.fixture
def people(system, roster):
    entries = [PersonnelProfile(employee_id=f'LIST-{index:03}', full_name=f'Person {index:02}',
               position='Staff', personnel_type='Staff', department='Operations', active=index != 0)
               for index in range(26)]
    db.session.add_all(entries)
    db.session.commit()
    return entries + [roster[0]]


def test_directory_pages_filters_and_saved_assignment_are_independent(system, roster, people):
    admin = login(system, 'admin-test')
    with rendered(system) as contexts:
        response = admin.get(f'/attendance/devices?page=2&registered={roster[0].id}')
    context = contexts[-1]
    assert response.status_code == 200
    assert len(context['people']) == 5 and context['pagination'].total == 27
    assert context['total_personnel'] == 27 and context['registered'].id == roster[0].id
    # The account picker still knows about assignments outside the directory page.
    option = next(option for option in context['account_options'] if option['id'] == roster[0].user_id)
    assert option['rfid_registered'] and option['personnel_id'] == roster[0].id
    assert b'id="personnel-registration" open' not in response.data
    with rendered(system) as contexts:
        response = admin.get('/attendance/devices?q=Person&department=Operations&active=yes&page=99&per_page=25')
    assert contexts[-1]['pagination'].total == 25
    assert len(contexts[-1]['people']) == 25 and contexts[-1]['pagination'].page == 1
    with rendered(system) as contexts:
        admin.get('/attendance/devices?q=LIST-000&active=no')
    assert [person.id for person in contexts[-1]['people']] == [people[0].id]


def test_daily_pages_do_not_truncate_statistics_or_leave_choices(system, roster, people):
    person, _, device, _, day = roster
    for index in range(12):
        db.session.add(AttendanceLog(personnel_id=person.id, device_id=device.id,
            event_id=f'list-event-{index}', occurred_at=datetime.now(timezone.utc),
            action='IN', accepted=True, message='Recorded'))
        db.session.add(EmployeeLeave(personnel_id=person.id, start_date=day, end_date=day,
            status='pending', reason=f'Request {index}'))
    db.session.commit()
    admin = login(system, 'admin-test')
    with rendered(system) as contexts:
        response = admin.get(f'/attendance/?date={day}&page=2&feed_page=2&leave_page=3')
    context = contexts[-1]
    assert response.status_code == 200 and len(context['rows']) == 5
    assert context['stats']['Personnel'] == 27 and len(context['people']) == 27
    assert len(context['logs']) == 5 and len(context['leaves']) == 2
    assert context['feed_pagination'].total == context['leave_pagination'].total == 12
    # Changing one list's page retains the others and returns to the relevant section.
    from app.attendance.listing import list_url
    with system.test_request_context(f'/attendance/?date={day}&page=2&feed_page=2&leave_page=3'):
        link = urlsplit(list_url(3, 'feed_page', 'attendance-feed'))
    assert parse_qs(link.query)['page'] == ['2'] and parse_qs(link.query)['leave_page'] == ['3']
    assert link.fragment == 'attendance-feed'
    with rendered(system) as contexts:
        admin.get(f'/attendance/?date={day}&status=Absent')
    assert contexts[-1]['pagination'].total == 1
    assert contexts[-1]['rows'][0]['person'].id == person.id
    assert contexts[-1]['stats']['Personnel'] == 27
    # Leave decisions return to the same filters and list pages.
    leave = context['leaves'][0]
    result = admin.post(f'/attendance/leave/{leave.id}?date={day}&page=2&leave_page=3', data={'status': 'approved'})
    assert parse_qs(urlsplit(result.location).query)['leave_page'] == ['3']
    assert urlsplit(result.location).fragment == 'leave-requests'


def test_report_pages_span_dates_and_downloads_include_every_match(system, roster, people):
    admin = login(system, 'admin-test')
    start = roster[4]
    end = start + timedelta(days=2)
    query = f'start_date={start}&end_date={end}&per_page=25&page=2'
    with rendered(system) as contexts:
        response = admin.get('/attendance/reports?' + query)
    context = contexts[-1]
    assert response.status_code == 200 and len(context['rows']) == 25
    assert context['pagination'].total == 81
    ordered = sorted(people, key=lambda person: (person.full_name, person.id))
    expected = [(start+timedelta(days=offset), person.id) for offset in range(3) for person in ordered]
    assert [(row['date'], row['person'].id) for row in context['rows']] == expected[25:50]
    response = admin.get('/attendance/reports?' + query + '&format=csv')
    data = list(csv.reader(StringIO(response.data.decode('utf-8-sig'))))
    assert len(data) == 82
    assert [(row[4], row[1]) for row in data[1:]] == [(str(day), db.session.get(PersonnelProfile,person_id).full_name) for day,person_id in expected]
    with rendered(system) as contexts:
        admin.get(f'/attendance/reports?start_date={start}&end_date={end}&page=999')
    assert contexts[-1]['pagination'].page == 17 and len(contexts[-1]['rows']) == 1


def test_invalid_pages_empty_results_and_official_access(system, roster, people):
    admin = login(system, 'admin-test')
    with rendered(system) as contexts:
        assert admin.get('/attendance/devices?page=invalid&per_page=10000').status_code == 200
    assert len(contexts[-1]['people']) == 5 and contexts[-1]['pagination'].page == 1
    for path in ('/attendance/', '/attendance/devices', '/attendance/reports'):
        with rendered(system) as contexts:
            response = admin.get(path + '?q=NoMatchingPersonnel&page=-4')
        assert response.status_code == 200 and contexts[-1]['pagination'].total == 0
        assert contexts[-1]['pagination'].page == 1
    staff = login(system, 'staff-test')
    for path in ('/attendance/', '/attendance/reports'):
        with rendered(system) as contexts:
            response = staff.get(path + '?page=999&per_page=50')
        assert response.status_code == 200 and contexts[-1]['pagination'].total == 1
        assert b'Person 00' not in response.data
        assert {row['person'].id for row in contexts[-1]['rows']} == {roster[0].id}
    assert staff.get('/attendance/devices').status_code == 403


def test_card_and_schedule_histories_have_separate_pages(system, roster):
    person, schedule, _, _, day = roster
    for index in range(12):
        db.session.add(RFIDCard(personnel_id=person.id, uid_hash=f'history-{index:056}',
            uid_suffix=f'{index:04}', active=False))
        db.session.add(EmployeeSchedule(personnel_id=person.id, name=f'History {index}',
            start_time=schedule.start_time, end_time=schedule.end_time, weekdays=[0, 1],
            effective_from=day-timedelta(days=30+index), effective_until=day-timedelta(days=1)))
    db.session.commit()
    with rendered(system) as contexts:
        response = login(system, 'admin-test').get(f'/attendance/personnel/{person.id}?cards_page=3&schedules_page=1')
    assert response.status_code == 200
    assert len(contexts[-1]['card_pagination'].items) == 3
    assert len(contexts[-1]['schedule_pagination'].items) == 5
    assert contexts[-1]['card_pagination'].total == contexts[-1]['schedule_pagination'].total == 13


def test_session_corrections_stay_with_the_visible_person_and_return_to_page(system, roster, people):
    from app.attendance.service import MANILA
    day = roster[4]
    at = datetime.combine(day, roster[1].start_time, MANILA)
    assert scan_at(system, roster, at, 'list-correction').status_code == 200
    session = db.session.scalar(db.select(AttendanceSession))
    admin = login(system, 'admin-test')
    with rendered(system) as contexts:
        response = admin.get(f'/attendance/?date={day}&page=6')
    assert response.status_code == 200 and b'Correct sessions (1)' in response.data
    assert contexts[-1]['rows'][-1]['person'].id == roster[0].id
    response = admin.get(f'/attendance/?date={day}&page=1')
    assert b'Correct sessions (1)' not in response.data
    response = admin.post(f'/attendance/sessions/{session.id}/adjust?date={day}&page=3&per_page=10',
        data={'time_in': at.strftime('%Y-%m-%dT%H:%M'), 'reason': 'Verified tap time'})
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query)['page'] == ['3']
    assert urlsplit(response.location).fragment == 'daily-records'
