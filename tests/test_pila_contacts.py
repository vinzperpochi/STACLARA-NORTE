from app.extensions import db
from app.models import User, AgencyHotline, HotlineVerification
from app.incidents.pila_contacts import import_pila_contacts
from app.incidents.service import classify
from test_system_integrity import system,login


def test_pila_contact_import_idempotent_visible_and_used_for_fire(system):
    from app.incidents.service import ensure_directory
    ensure_directory();actor=db.session.scalar(db.select(User).where(User.username=='admin-test'))
    assert import_pila_contacts(actor)==7;db.session.commit()
    assert import_pila_contacts(actor)==0;db.session.commit()
    assert db.session.scalar(db.select(db.func.count(AgencyHotline.id)))==7
    assert db.session.scalar(db.select(db.func.count(HotlineVerification.id)))==7
    result=classify('FIRE');assert any(c['tel']=='0495590511' for c in result['contacts'])
    page=login(system).get('/incidents/directory?contacts_per_page=10')
    assert page.status_code==200
    for number in ['0920-959-7911','0961-131-6791','0956-814-3476','0939-555-7802','0963-607-5123','(049) 559-0511','(049) 554-6451']: assert number.encode() in page.data
    assert b'tel:09636075123' in page.data
