from datetime import date
from app.extensions import db
from app.models import Request,DocumentType,Role,Permission,FeeConfiguration,User
from app.documents.workflow import ensure_catalog
from test_system_integrity import system,login,image_bytes

def test_staff_walk_in_id_and_purpose_and_role_boundary(system):
    documents=ensure_catalog();document=next(d for d in documents if d.code=='BARANGAY_CLEARANCE')
    resident=db.session.scalar(db.select(User).where(User.username=='resident-test')).resident
    staff=login(system,'staff-test')
    assert staff.get('/official/document-requests/walk-in?q=Maria').status_code==200
    result=staff.post('/official/document-requests/walk-in',data={'resident_id':resident.id,'document_type_id':document.id,'description':'Employment purpose', 'id_image':(image_bytes(),'identity.png','image/png')})
    assert result.status_code==302
    item=db.session.scalar(db.select(Request));assert item.description=='Employment purpose' and item.additional_data['intake_channel']=='WALK_IN' and item.status=='PENDING'
    assert any(requirement.filename for requirement in item.requirements)
    uploaded=next(requirement for requirement in item.requirements if requirement.filename)
    image=staff.get(f'/official/document-requests/{item.id}/requirements/{uploaded.id}/view'); assert image.status_code==200 and image.mimetype.startswith('image/');image.close()
    staff.post(f'/official/document-requests/{item.id}/walk-in-edit',data={'description':'Corrected employment purpose'})
    assert item.description=='Corrected employment purpose'
    assert staff.get(result.location).status_code==200
    assert login(system).get('/official/document-requests/walk-in').status_code==403
    count=db.session.scalar(db.select(db.func.count(Request.id)))
    staff.post('/official/document-requests/walk-in',data={'resident_id':resident.id,'document_type_id':999999,'description':'Invalid'})
    assert db.session.scalar(db.select(db.func.count(Request.id)))==count

def test_permission_configuration_enforces_document_access(system):
    admin=login(system,'admin-test');assert admin.get('/admin/roles').status_code==200
    role=db.session.scalar(db.select(Role).where(Role.name=='Barangay Official'))
    workspace=db.session.scalar(db.select(Permission).where(Permission.resource=='workspace',Permission.action=='access'))
    review=db.session.scalar(db.select(Permission).where(Permission.resource=='documents',Permission.action=='review'))
    staff=login(system,'staff-test');assert staff.get('/official/document-requests').status_code==200
    admin.post(f'/admin/roles/{role.id}/access',data={'permission_id':[workspace.id]})
    assert staff.get('/official/document-requests').status_code==403 and staff.get('/official/document-requests/walk-in').status_code==403
    admin.post(f'/admin/roles/{role.id}/access',data={'permission_id':[workspace.id,review.id]})
    assert staff.get('/official/document-requests/walk-in').status_code==200
    resident_role=db.session.scalar(db.select(Role).where(Role.name=='Resident'))
    admin.post(f'/admin/roles/{resident_role.id}/access',data={'permission_id':[review.id]})
    assert review not in resident_role.permissions
    assert staff.post(f'/admin/roles/{role.id}/access',data={'permission_id':[]}).status_code==403

def test_admin_crud_validation_and_archival(system):
    admin=login(system,'admin-test')
    assert admin.post('/admin/document-types',data={'code':'TEST_DOC','name':'Test document','base_fee':'-1'}).status_code==302
    assert not db.session.scalar(db.select(DocumentType).where(DocumentType.code=='TEST_DOC'))
    admin.post('/admin/document-types',data={'code':'TEST_DOC','name':'Test document','base_fee':'20'})
    document=db.session.scalar(db.select(DocumentType).where(DocumentType.code=='TEST_DOC'));assert document
    admin.post(f'/admin/document-types/{document.id}/edit',data={'code':'TEST_DOC','name':'Updated document','base_fee':'25','status':'active'})
    assert document.name=='Updated document' and document.base_fee==25
    admin.post(f'/admin/document-types/{document.id}/delete');assert document.status=='inactive'
    admin.post(f'/admin/document-types/{document.id}/edit',data={'code':'TEST_DOC','name':'Updated document','base_fee':'25','status':'active'});assert document.status=='active'
    admin.post('/admin/fees',data={'document_type_id':document.id,'amount':'5','effective_from':date.today().isoformat()})
    fee=db.session.scalar(db.select(FeeConfiguration));assert fee
    admin.post(f'/admin/fees/{fee.id}/delete');assert fee.status=='inactive'
    role=db.session.scalar(db.select(Role).where(Role.name=='System Administrator'))
    admin.post(f'/admin/roles/{role.id}/delete');assert db.session.get(Role,role.id)
    assert login(system,'staff-test').get(f'/admin/document-types/{document.id}/edit').status_code==403

def test_permission_and_role_crud_protects_builtin_access(system):
    admin=login(system,'admin-test');admin.get('/admin/roles')
    baseline=db.session.scalar(db.select(Permission).where(Permission.resource=='documents',Permission.action=='review'))
    assert admin.get('/admin/permissions').status_code==200
    admin.post(f'/admin/permissions/{baseline.id}/delete');assert db.session.get(Permission,baseline.id)
    admin.post(f'/admin/permissions/{baseline.id}/edit',data={'resource':'unsafe','action':'access','description':'Attempted rename'})
    assert baseline.resource=='documents'
    admin.post('/admin/permissions',data={'resource':'custom_reports','action':'view','description':'Custom grant'})
    custom=db.session.scalar(db.select(Permission).where(Permission.resource=='custom_reports'));assert custom
    admin.post('/admin/permissions',data={'resource':'custom_reports','action':'view','description':'Duplicate'})
    assert db.session.scalar(db.select(db.func.count(Permission.id)).where(Permission.resource=='custom_reports'))==1
    admin.post(f'/admin/permissions/{custom.id}/edit',data={'resource':'custom_reports','action':'view','description':'Updated grant'})
    assert custom.description=='Updated grant'
    identifier=custom.id;admin.post(f'/admin/permissions/{identifier}/delete');assert db.session.get(Permission,identifier) is None
    admin.post('/admin/roles',data={'name':'Test clerk','description':'Custom role'})
    role=db.session.scalar(db.select(Role).where(Role.name=='Test clerk'));assert role
    admin.post(f'/admin/roles/{role.id}/edit',data={'name':'Updated clerk','description':'Updated role'})
    assert role.name=='Updated clerk'
    identifier=role.id;admin.post(f'/admin/roles/{identifier}/delete');assert db.session.get(Role,identifier) is None
