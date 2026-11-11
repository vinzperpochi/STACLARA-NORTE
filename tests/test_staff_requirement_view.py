from pathlib import Path
import pytest
from app.extensions import db
from app.models import AuditLog
from test_system_integrity import system, login, image_bytes, requirement_fixture

@pytest.mark.parametrize('image_format,filename,mimetype',[('PNG','id.png','image/png'),('JPEG','id.jpg','image/jpeg')])
def test_staff_views_uploaded_requirement_inline(system,image_format,filename,mimetype):
    item,requirement=requirement_fixture()
    resident=login(system)
    resident.post(f'/resident/documents/{item.id}/requirements/{requirement.id}/upload',data={'requirement_file':(image_bytes(image_format),filename,mimetype)})
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
    assert response.data==(Path(system.config['STORAGE_ROOT'])/'document_requirements'/requirement.filename).read_bytes()
    response.close()
    assert db.session.scalar(db.select(AuditLog).where(AuditLog.action=='DOCUMENT_REQUIREMENT_VIEW'))
    assert staff.get(url.replace(f'/{item.id}/requirements/',f'/{item.id+100}/requirements/')).status_code==404
    assert system.test_client().get(url).status_code==302
    assert resident.get(url).status_code==403
    (Path(system.config['STORAGE_ROOT'])/'document_requirements'/requirement.filename).unlink()
    assert staff.get(url).status_code==404
