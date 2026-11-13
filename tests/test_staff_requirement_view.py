import pytest
from app.extensions import db
from app.models import AuditLog, DocumentRequirement
from test_system_integrity import system, login, image_bytes, requirement_fixture

@pytest.mark.parametrize('image_format,filename,mimetype',[('PNG','id.png','image/png'),('JPEG','id.jpg','image/jpeg')])
def test_staff_views_uploaded_requirement_inline(system,tmp_path,image_format,filename,mimetype):
    item,requirement=requirement_fixture()
    resident=login(system)
    resident.post(f'/resident/documents/{item.id}/requirements/{requirement.id}/upload',data={'requirement_file':(image_bytes(image_format),filename,mimetype)})
    system.config['STORAGE_ROOT'] = str(tmp_path)
    db.session.expire_all()
    resident_url = f'/resident/documents/{item.id}/requirements/{requirement.id}'
    detail = resident.get(f'/resident/documents/{item.id}')
    assert b'Your ID is saved on this request.' in detail.data
    assert (resident_url + '/remove').encode() not in detail.data
    assert resident.post(resident_url + '/remove').status_code == 403
    original_filename = requirement.filename
    resident.post(resident_url + '/upload', data={
        'requirement_file': (image_bytes(image_format), filename, mimetype),
    })
    assert requirement.filename == original_filename
    staff=login(system,'staff-test')
    url=f'/official/document-requests/{item.id}/requirements/{requirement.id}/view'
    detail=staff.get(f'/official/document-requests/{item.id}')
    assert detail.status_code==200
    assert b'<img' in detail.data and (b'src="'+url.encode()+b'"') in detail.data
    assert url.encode() in detail.data and b'View full-size ID / image' in detail.data
    response=staff.get(url)
    assert response.status_code==200 and response.mimetype==mimetype
    assert 'attachment' not in response.headers.get('Content-Disposition','')
    assert response.cache_control.no_store
    assert response.data == requirement.image_data
    saved = resident.get(resident_url + '/view')
    assert saved.status_code == 200 and saved.data == response.data
    saved.close()
    response.close()
    assert db.session.scalar(db.select(AuditLog).where(AuditLog.action=='DOCUMENT_REQUIREMENT_VIEW'))
    assert staff.get(url.replace(f'/{item.id}/requirements/',f'/{item.id+100}/requirements/')).status_code==404
    assert system.test_client().get(url).status_code==302
    assert resident.get(url).status_code==403


def test_admin_receives_every_uploaded_requirement(system, tmp_path):
    item, identity = requirement_fixture()
    proof = DocumentRequirement(request=item, requirement_name='Proof of residency')
    db.session.add(proof)
    db.session.commit()
    resident = login(system)
    for requirement in (identity, proof):
        result = resident.post(
            f'/resident/documents/{item.id}/requirements/{requirement.id}/upload',
            data={'requirement_file': (image_bytes(), 'requirement.png', 'image/png')},
            follow_redirects=True,
        )
        assert result.status_code == 200
    system.config['STORAGE_ROOT'] = str(tmp_path)
    db.session.expire_all()
    admin = login(system, 'admin-test')
    admin_page = admin.get(f'/official/document-requests/{item.id}')
    resident_page = resident.get(f'/resident/documents/{item.id}')
    for requirement in (identity, proof):
        path = f'/documents/{item.id}/requirements/{requirement.id}/view'
        resident_url = '/resident' + path
        admin_url = path.replace('/documents/', '/official/document-requests/', 1)
        assert f'src="{resident_url}"'.encode() in resident_page.data
        assert f'src="{admin_url}"'.encode() in admin_page.data
        assert admin.get(admin_url).data == resident.get(resident_url).data
        assert requirement.image_data
