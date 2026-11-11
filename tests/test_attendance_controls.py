from html.parser import HTMLParser
import pytest

from app.extensions import db
from app.models import EmployeeSchedule, PersonnelProfile, User
from test_system_integrity import system, login
from test_attendance_operations import roster
from test_rfid_registration import FIRST_SCHEDULE, start


class Controls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs=[];self.links=[]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag=='input': self.inputs.append(values)
        if tag=='a' and 'ops-page-link' in values.get('class','').split(): self.links.append(values)


@pytest.mark.parametrize('chosen_days',[['0','3','6'],['0','1','2','3','4','5','6']])
def test_independent_duty_days_survive_validation_and_save_together(system, roster, chosen_days):
    admin=login(system,'admin-test')
    token=start(admin,roster[2])
    result=system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'00112233'})
    assert result.json['success']
    form={**FIRST_SCHEDULE,'action':'register_card','account_mode':'none',
          'capture_id':token,'first_name':'Multiple','last_name':'Days',
          'barangay_role':'Barangay Staff','weekdays':chosen_days}
    invalid=admin.post('/attendance/devices',data={**form,'end_time':form['start_time']})
    assert invalid.status_code==200
    controls=[v for v in Controls(invalid.get_data(as_text=True)).inputs if v.get('name')=='weekdays']
    assert len(controls)==7 and all(v['type']=='checkbox' for v in controls)
    assert [v['value'] for v in controls if 'checked' in v]==chosen_days
    assert admin.post('/attendance/devices',data=form).status_code==302
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.full_name=='Multiple Days'))
    assert person.schedules[0].weekdays==[int(day) for day in chosen_days]


def test_add_duty_schedule_saves_multiple_days_and_rejects_empty_selection(system, roster):
    person=roster[0];admin=login(system,'admin-test')
    form={**FIRST_SCHEDULE,'action':'schedule','name':'Alternate duty days',
          'weekdays':['1','4','5'],'cutoff_minutes':'120',
          'minimum_session_minutes':'1','max_sessions':'1'}
    assert admin.post(f'/attendance/personnel/{person.id}',data=form).status_code==302
    schedule=db.session.scalar(db.select(EmployeeSchedule).where(EmployeeSchedule.name=='Alternate duty days'))
    assert schedule.weekdays==[1,4,5]
    assert admin.post(f'/attendance/personnel/{person.id}',data={**form,'name':'Empty duty','weekdays':[]}).status_code==302
    assert db.session.scalar(db.select(EmployeeSchedule).where(EmployeeSchedule.name=='Empty duty')) is None


def test_each_attendance_page_has_the_correct_current_navigation(system, roster):
    admin=login(system,'admin-test')
    for url,selected in [('/attendance/','/attendance/'),('/attendance/devices','/attendance/devices'),
                         ('/attendance/reports','/attendance/reports'),
                         (f'/attendance/personnel/{roster[0].id}','/attendance/devices')]:
        response=admin.get(url)
        assert response.status_code==200
        controls=Controls(response.get_data(as_text=True))
        assert len(controls.links)==3
        assert [link['href'] for link in controls.links if link.get('aria-current')=='page']==[selected]


def test_report_personnel_picker_respects_account_access(system, roster):
    other_user=db.session.scalar(db.select(User).where(User.username=='other-test'))
    other=PersonnelProfile(user_id=other_user.id,employee_id='PRIVATE-002',full_name='Other Private Person',position='Staff',personnel_type='Staff')
    db.session.add(other);db.session.commit()
    staff=login(system,'staff-test')
    response=staff.get('/attendance/reports')
    assert response.status_code==200 and b'Other Private Person' not in response.data
    assert roster[0].full_name.encode() in response.data
    response=staff.get(f'/attendance/reports?personnel_id={other.id}')
    assert response.status_code==200 and b'Other Private Person' not in response.data
    assert b'Other Private Person' in login(system,'admin-test').get('/attendance/reports').data
