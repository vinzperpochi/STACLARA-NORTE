"""Personnel, initial schedule and scanned card use one atomic registration."""
from app.extensions import db
from app.models import PersonnelProfile, RFIDCard, EmployeeSchedule
from test_system_integrity import system, login, image_bytes
from test_attendance_operations import roster
from test_rfid_registration import start, FIRST_SCHEDULE, unregistered_person


def test_combined_save_is_atomic_and_retains_capture_after_validation_error(system,roster):
    admin=login(system,'admin-test');token=start(admin,roster[2])
    system.test_client().post('/attendance/api/registration-tap',headers=roster[3],json={'capture_id':token,'uid':'00112233'})
    form={**FIRST_SCHEDULE,'action':'register_card','capture_id':token,'first_name':'Combined','last_name':'Staff','barangay_role':'Barangay Staff','employee_id':'EMP-COMBINED','department':'Office','email':'staff@example.com','mobile':'09123456789','employment_status':'Contractual'}
    response=admin.post('/attendance/devices',data={**form,'end_time':'08:00'})
    assert response.status_code==200
    assert db.session.scalar(db.select(db.func.count(PersonnelProfile.id)))==1
    assert db.session.scalar(db.select(db.func.count(EmployeeSchedule.id)))==1
    assert db.session.scalar(db.select(db.func.count(RFIDCard.id)))==1
    assert admin.get('/attendance/registration/'+token).json['state']=='captured'
    response=admin.post('/attendance/devices',data={**form,'photo':(image_bytes(),'photo.png','image/png')})
    assert response.status_code==302
    person=db.session.scalar(db.select(PersonnelProfile).where(PersonnelProfile.employee_id=='EMP-COMBINED'))
    assert person.full_name=='Combined Staff' and person.email=='staff@example.com' and person.department=='Office'
    assert person.photo_filename and person.user_id is None
    assert len(person.cards)==1 and len(person.schedules)==1
    assert person.schedules[0].start_time.hour==8 and person.schedules[0].end_time.hour==17
    assert person.schedules[0].weekdays==[0,1,2,3,4]
    assert admin.get('/attendance/registration/'+token).json['state']=='consumed'


def test_one_navigation_and_directory_includes_personnel_without_cards(system,roster):
    admin=login(system,'admin-test')
    legacy=admin.get('/attendance/personnel')
    assert legacy.status_code==302 and legacy.location.endswith('/attendance/devices')
    person=PersonnelProfile(employee_id='OLD-UNASSIGNED',full_name='Existing Unassigned',position='Barangay Staff',personnel_type='Staff',active=False)
    db.session.add(person);db.session.commit()
    page=admin.get('/attendance/devices').get_data(as_text=True)
    assert 'Existing Unassigned' in page and 'No RFID card assigned yet.' in page
    assert 'Save personnel, schedule &amp; RFID' in page
    assert 'name="start_time"' in page and 'name="photo"' in page
    assert 'href="/attendance/personnel"' not in page
    assert 'Personnel Management' not in page and '>RFID Devices<' not in page
    assert admin.get('/attendance/personnel/'+str(person.id)).status_code==200


def test_existing_profile_account_and_schedule_are_preserved(system,roster):
    person,schedule,device,headers,_=roster
    unregistered_person(person)
    admin=login(system,'admin-test');token=start(admin,device)
    system.test_client().post('/attendance/api/registration-tap',headers=headers,json={'capture_id':token,'uid':'11229988'})
    linked=person.user_id;existing_schedule=schedule.id
    assert admin.post('/attendance/devices',data={**FIRST_SCHEDULE,'action':'register_card','account_mode':'existing','user_id':person.user_id,'capture_id':token,'first_name':'Test','last_name':'Official','barangay_role':'Barangay Secretary'}).status_code==302
    db.session.refresh(person)
    assert person.user_id==linked and len(person.schedules)==1 and person.schedules[0].id==existing_schedule
    assert len(person.cards)==1
    # Optional fields remain optional when editing the combined record.
    response=admin.post(f'/attendance/personnel/{person.id}',data={'action':'details','full_name':'Test Official','position':'Barangay Secretary','department':'','mobile':'','email':'','employment_status':''})
    assert response.status_code==302
