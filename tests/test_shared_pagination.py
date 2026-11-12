"""Shared paging keeps complete results, filters, totals and account boundaries."""
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlsplit

from flask import render_template

from app.extensions import db
from app.models import (User, Role, Resident, Notification, EvacuationCenter, EmergencyAlert,
    DocumentSignatory, BeneficiaryRegistry, AssistanceRecord, ResidentComplaint, IncidentCategory)
from app.pagination import Pagination, pagination_url, paginate_items
from test_system_integrity import system, login
from test_attendance_lists import rendered


def user(name):
    return db.session.scalar(db.select(User).where(User.username == name))


def test_five_record_default_matches_reference_at_first_middle_and_last_page(system):
    records = list(range(22))
    for requested, expected_page, expected_items in (
        (1, 1, records[:5]),
        (3, 3, records[10:15]),
        (999, 5, records[20:]),
    ):
        with system.test_request_context(f'/official/residents?page={requested}&q=Maria'):
            pagination = paginate_items(records)
            html = render_template('partials/_pagination.html', pagination=pagination)
        assert pagination.page == expected_page and pagination.per_page == 5
        assert pagination.items == expected_items and pagination.total == 22
        assert 'pagination-controls' not in html and 'pagination-summary' not in html
        assert 'name="per_page"' in html and 'value="all"' in html
        assert 'name="q" value="Maria"' in html
        assert 'name="page"' not in html


def test_last_page_matches_reference_and_preserves_multiple_filters(system):
    with system.test_request_context('/official/residents?page=50&q=Maria&tag=a&tag=b&format=csv&_anchor=bad'):
        html = render_template('partials/_pagination.html', pagination=Pagination([],50,10,500,50))
        assert 'pagination-summary' not in html
        assert 'pagination-controls' not in html
        link = urlsplit(pagination_url(2,'alerts_page','alerts'))
        args = parse_qs(link.query)
        assert args['tag'] == ['a','b'] and args['q'] == ['Maria']
        assert args['page'] == ['50'] and args['alerts_page'] == ['2']
        assert 'format' not in args and '_anchor' not in args and link.fragment == 'alerts'


def test_notifications_include_records_beyond_old_cap_and_filter_before_paging(system):
    owner, other = user('resident-test'), user('other-test')
    stamp = datetime(2026,11,5,tzinfo=timezone.utc)
    rows = [Notification(user_id=owner.id,title=f'Notice {i:03}',message='General announcement',
                         is_read=False,created_at=stamp) for i in range(125)]
    rows[0].title = 'Older needle'
    rows[0].message = 'Health clinic information'
    db.session.add_all(rows + [Notification(user_id=other.id,title='Private needle',message='Health secret')])
    db.session.commit()
    client = login(system)
    ids = []
    for page in range(1,26):
        with rendered(system) as contexts:
            response = client.get(f'/resident/notifications?page={page}')
        context = contexts[-1]
        assert response.status_code == 200 and context['pagination'].total == 125
        assert context['pagination'].per_page == 5
        ids.extend(item.id for item in context['notifications'])
        assert all(item.user_id == owner.id for item in context['notifications'])
    assert len(set(ids)) == len(ids) == 125
    with rendered(system) as contexts:
        response = client.get('/resident/notifications?q=needle&category=health&unread=1&page=999')
    assert response.status_code == 200
    assert contexts[-1]['pagination'].total == 1 and contexts[-1]['pagination'].page == 1
    assert contexts[-1]['notifications'][0].title == 'Older needle'
    assert b'Private needle' not in response.data


def test_drrm_lists_page_independently_and_keep_all_center_options(system):
    db.session.add_all([EvacuationCenter(name=f'Center {i:02}',address='Test location',capacity=50) for i in range(23)])
    db.session.add_all([EmergencyAlert(title=f'Alert {i:02}',message='Test advisory',issued_at=datetime.now(timezone.utc),status='PUBLISHED') for i in range(16)])
    db.session.commit()
    with rendered(system) as contexts:
        response = login(system,'staff-test').get('/official/drrm?centers_page=5&alerts_page=4')
    context = contexts[-1]
    assert response.status_code == 200
    assert len(context['centers']) == 3 and context['pagers']['centers'].total == 23
    assert len(context['alerts']) == 1 and context['pagers']['alerts'].total == 16
    assert len(context['all_centers']) == 23
    assert b'name="centers_page" value="5"' in response.data
    assert b'name="alerts_per_page"' in response.data
    assert b'drrm-centers' in response.data


def test_signatory_history_is_bounded_and_does_not_page_template_choices(system):
    administrator=user('admin-test')
    db.session.add_all([DocumentSignatory(full_name=f'Official {i:02}',designation='Authorized signatory',
        authorized_by_id=administrator.id,effective_from=date(2026,1,1),status='active') for i in range(24)])
    db.session.commit()
    with rendered(system) as contexts:
        response=login(system,'admin-test').get('/official/document-settings?signatories_page=5&types_page=1')
    context=contexts[-1]
    assert response.status_code==200 and len(context['signatories'])==4
    assert context['signatory_pagination'].total==24 and len(context['codes'])==7
    assert context['type_pagination'].total>=7


def test_assistance_history_has_no_twenty_record_cap(system):
    beneficiary=BeneficiaryRegistry(resident_id=user('resident-test').resident_id,category='SENIOR',registered_date=date(2026,1,1))
    db.session.add(beneficiary); db.session.flush()
    db.session.add_all([AssistanceRecord(beneficiary_id=beneficiary.id,assistance_type='Test distribution',
        assistance_date=date(2026,11,5),quantity=1) for _ in range(27)])
    db.session.commit()
    with rendered(system) as contexts:
        response=login(system,'staff-test').get('/official/welfare?assistance_page=6')
    assert response.status_code==200
    assert len(contexts[-1]['assistance'])==2 and contexts[-1]['assistance_pagination'].total==27
    assert contexts[-1]['pagination'].total==1


def test_alert_history_uses_shared_pager_and_excludes_unpublished(system):
    db.session.add_all([EmergencyAlert(title=f'Public {i}',message='Advisory',issued_at=datetime.now(timezone.utc),status='PUBLISHED') for i in range(12)])
    db.session.add(EmergencyAlert(title='Private draft',message='Not public',issued_at=datetime.now(timezone.utc),status='DRAFT'))
    db.session.commit()
    with rendered(system) as contexts:
        response=login(system).get('/resident/emergency-alerts?page=3')
    assert response.status_code==200
    assert contexts[-1]['pagination'].total==12 and len(contexts[-1]['alerts'])==2
    assert b'name="per_page"' in response.data and b'Private draft' not in response.data


def test_search_reaches_results_beyond_the_twenty_record_cap(system):
    db.session.add_all([Resident(first_name='Searchmatch',last_name=f'Person {i:02}',birth_date=date(1990,1,1),status='active') for i in range(25)])
    db.session.commit()
    with rendered(system) as contexts:
        response=login(system,'staff-test').get('/search?q=Searchmatch&residents_page=5&cases_page=1')
    assert response.status_code==200
    assert len(contexts[-1]['residents'])==5 and contexts[-1]['pagers']['residents'].total==25
    assert b'name="q" value="Searchmatch"' in response.data
    assert b'name="residents_per_page"' in response.data
    assert login(system).get('/search?q=Searchmatch').status_code==403


def test_account_approvals_have_stable_disjoint_pages(system):
    role=db.session.scalar(db.select(Role).where(Role.name=='Resident'))
    stamp=datetime(2026,11,5,tzinfo=timezone.utc)
    for i in range(23):
        resident=Resident(first_name='Pending',last_name=f'Applicant {i:02}',birth_date=date(1990,1,1),status='pending')
        account=User(username=f'pending-{i}',email=f'pending-{i}@example.com',password_hash=user('admin-test').password_hash,
            resident=resident,is_active=False,status='pending',created_at=stamp)
        account.roles.append(role);db.session.add(account)
    db.session.commit()
    client=login(system,'staff-test')
    ids=[]
    for number in range(1,6):
        with rendered(system) as contexts:
            response=client.get(f'/official/account-approvals?page={number}')
        assert response.status_code==200 and contexts[-1]['pagination'].total==23
        ids.extend(item.id for item in contexts[-1]['pending_accounts'])
    assert len(set(ids))==len(ids)==23


def test_incident_report_exports_all_matches_while_preview_is_paginated(system):
    import csv
    from io import StringIO
    from app.incidents.service import ensure_directory
    ensure_directory(); db.session.commit()
    category=db.session.scalar(db.select(IncidentCategory))
    stamp=datetime.now(timezone.utc)
    for i in range(24):
        db.session.add(ResidentComplaint(resident_id=user('resident-test').resident_id,reference=f'PAGING-{i:03}',
            title='Test report',category_id=category.id,description='Synthetic report',incident_at=stamp,
            location='Test location',urgency='normal',classification='REVIEW',routing_snapshot={},created_at=stamp))
    db.session.commit()
    client=login(system,'admin-test')
    query=f'start_date={stamp.date()}&end_date={stamp.date()}&page=5'
    with rendered(system) as contexts:
        response=client.get('/incidents/reports?'+query)
    assert response.status_code==200
    assert len(contexts[-1]['items'])==4 and contexts[-1]['pagination'].total==24
    response=client.get('/incidents/reports?'+query+'&format=csv')
    assert response.status_code==200
    rows=list(csv.reader(StringIO(response.data.decode('utf-8-sig'))))
    assert len(rows)==25
