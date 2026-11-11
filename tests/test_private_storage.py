from pathlib import Path
from uuid import uuid4
import pytest

@pytest.fixture
def upload_tmp():
    path=Path('.test-storage')/uuid4().hex
    path.mkdir(parents=True)
    return path.resolve()
from app.extensions import db
from app.private_storage import private_image_path
from app.documents.workflow import evidence_available
from test_system_integrity import system, login
from test_document_review import initial_request


@pytest.mark.parametrize("request_upload",[False,True])
def test_private_id_found_in_old_project_layout_after_storage_root_changes(system,upload_tmp,request_upload):
    resident,item,client,staff,checks=initial_request(system)
    evidence=item.active_requirements[0]
    original=Path(system.config['STORAGE_ROOT'])
    # Use a synthetic project so fallback roots never touch real resident uploads.
    project=upload_tmp/'project'
    template_loader=system.jinja_loader
    system.root_path=str(project/'app')
    system.jinja_loader=template_loader
    folder='document_requirements' if request_upload else 'registration_documents'
    if request_upload:
        evidence.filename=resident.philsys_card_filename
        db.session.commit()
    old=project.parent/'instance'/folder;old.mkdir(parents=True)
    (old/resident.philsys_card_filename).write_bytes((original/'registration_documents'/resident.philsys_card_filename).read_bytes())
    system.config['STORAGE_ROOT']=str(project/'instance')
    assert evidence_available(evidence)
    url=f'/official/document-requests/{item.id}/requirements/{evidence.id}/view'
    response=staff.get(url);assert response.status_code==200 and response.mimetype=='image/png'
    assert 'no-store' in response.headers['Cache-Control']
    assert client.get(f'/resident/documents/{item.id}/requirements/{evidence.id}/view').status_code==200
    assert login(system,'other-test').get(f'/resident/documents/{item.id}/requirements/{evidence.id}/view').status_code==404


def test_private_lookup_prefers_configured_root_and_rejects_traversal(system,upload_tmp):
    system.root_path=str(upload_tmp/'project'/'app')
    system.config['STORAGE_ROOT']=str(upload_tmp/'current')
    current=upload_tmp/'current'/'document_requirements';current.mkdir(parents=True)
    old=upload_tmp/'instance'/'document_requirements';old.mkdir(parents=True)
    (current/'id.png').write_bytes(b'current');(old/'id.png').write_bytes(b'old')
    assert private_image_path('document_requirements','id.png')==current/'id.png'
    assert private_image_path('document_requirements','../id.png') is None
    assert private_image_path('document_requirements','..\\id.png') is None
    assert private_image_path('document_requirements',str(current/'id.png')) is None
    assert private_image_path('document_requirements','missing.png') is None
    assert private_image_path('../document_requirements','id.png') is None
    assert private_image_path('document_requirements','id.html') is None


def test_relative_storage_and_log_paths_are_project_based(monkeypatch):
    import importlib,config
    monkeypatch.setenv('STORAGE_ROOT','instance');monkeypatch.setenv('LOG_FILE','instance/logs/app.log')
    importlib.reload(config)
    assert Path(config.BaseConfig.STORAGE_ROOT)==config.BASE_DIR/'instance'
    assert Path(config.BaseConfig.LOG_FILE)==config.BASE_DIR/'instance'/'logs'/'app.log'
