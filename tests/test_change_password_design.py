from datetime import date
import pytest
from app.extensions import db
from app.models import User,Resident,Role
from test_system_integrity import system,login

@pytest.mark.parametrize('username,workspace',[('resident-test','workspace-resident'),('staff-test','workspace-official'),('admin-test','workspace-admin')])
def test_shared_change_password_design_and_validation(system,username,workspace):
    client=login(system,username)
    user=db.session.scalar(db.select(User).where(User.username==username))
    original=user.password_hash
    page=client.get('/auth/change-password')
    assert page.status_code==200
    html=page.get_data(as_text=True)
    assert workspace in html and 'Set a new password' in html
    assert 'Old Password' in html and 'Save New Password' in html
    assert 'Identify Account' not in html
    assert 'change-password.css' in html and 'change-password.js' in html
    assert html.count('data-cp-toggle=')==3
    assert 'name="csrf_token"' in html
    assert 'autocomplete="current-password"' in html
    assert 'data-password-strength' in html
    fields={'current_password':'Wrong-password!','new_password':'Updated-Password-2026!','password_confirmation':'Updated-Password-2026!'}
    rejected=client.post('/auth/change-password',data=fields)
    assert rejected.status_code==200 and b'Old password is incorrect.' in rejected.data
    assert fields['new_password'].encode() not in rejected.data
    db.session.refresh(user);assert user.password_hash==original
    fields['current_password']='Strong-test-password!';fields['password_confirmation']='Different-Password-2026!'
    assert client.post('/auth/change-password',data=fields).status_code==200
    db.session.refresh(user);assert user.password_hash==original
    fields['new_password']=fields['password_confirmation']='Short1A'
    assert client.post('/auth/change-password',data=fields).status_code==200
    db.session.refresh(user);assert user.password_hash==original
    fields['new_password']=fields['password_confirmation']='Updated-Password-2026!'
    assert client.post('/auth/change-password',data=fields).status_code==302
    db.session.refresh(user);assert user.check_password(fields['new_password'])

def test_admin_with_resident_identity_keeps_admin_workspace(system):
    user=db.session.scalar(db.select(User).where(User.username=='admin-test'))
    user.resident=Resident(first_name='QA',last_name='Administrator',birth_date=date(1990,1,1),status='active')
    user.roles.append(db.session.scalar(db.select(Role).where(Role.name=='Resident')))
    db.session.commit()
    html=login(system,'admin-test').get('/auth/change-password').get_data(as_text=True)
    assert 'workspace-admin' in html
    assert 'workspace-resident' not in html
