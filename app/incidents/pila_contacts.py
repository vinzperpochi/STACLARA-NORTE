"""Explicit, idempotent import of contacts published by Pila LGU."""
from datetime import date
from sqlalchemy import select
from app.extensions import db
from app.models import GovernmentAgency, AgencyHotline, HotlineVerification, ComplaintAuditLog

POSTER='https://elgu-news-cdn.e.gov.ph/pila-laguna/uploads/767268710_1050971091001875_8130768944408381311_n.jpg'
CONTACT_PAGE='https://elgu-pila-laguna-news.e.gov.ph/CONTACTUS'
VERIFIED_ON=date(2026,10,9)
CONTACTS=[
    ('PILA_ACTION','Pila Action Center','0920-959-7911','Smart; service hours not published',POSTER,True),
    ('PILA_ACTION','Pila Action Center','0961-131-6791','Smart; service hours not published',POSTER,True),
    ('PNP','Pila Police Station / PNP','0956-814-3476','Globe; service hours not published',POSTER,True),
    ('PNP','Pila Police Station / PNP','0939-555-7802','Smart; service hours not published',POSTER,True),
    ('BFP','Pila Bureau of Fire Protection / Fire Station','(049) 559-0511','Landline; service hours not published',POSTER,True),
    ('BFP','Pila Bureau of Fire Protection / Fire Station','0963-607-5123','Smart; service hours not published',POSTER,True),
    ('PILA_LGU','Pila Municipal General Contact','(049) 554-6451','General office inquiries; hours not published',CONTACT_PAGE,False),
]


def import_pila_contacts(actor):
    if not actor.is_active or actor.status!='active' or not any(role.name=='System Administrator' for role in actor.roles):
        raise ValueError('An active administrator must authorize this directory import.')
    changed=0
    for code,name,number,hours,source,emergency in CONTACTS:
        agency=db.session.scalar(select(GovernmentAgency).where(GovernmentAgency.code==code))
        if not agency:
            agency=GovernmentAgency(code=code,name=name,service_area='Pila, Laguna',jurisdiction='Local contact published by Pila LGU')
            db.session.add(agency);db.session.flush()
        agency.name=name;agency.active=True
        hotline=db.session.scalar(select(AgencyHotline).where(AgencyHotline.agency_id==agency.id,AgencyHotline.number==number))
        if hotline and hotline.active and hotline.verified_on==VERIFIED_ON and hotline.verification_source==source: continue
        if not hotline: hotline=AgencyHotline(agency_id=agency.id,number=number);db.session.add(hotline)
        hotline.availability=hours;hotline.coverage='Pila, Laguna';hotline.verified_on=VERIFIED_ON;hotline.verification_source=source;hotline.active=True;hotline.emergency=emergency
        db.session.flush()
        db.session.add(HotlineVerification(hotline_id=hotline.id,actor_id=actor.id,source=source,verified_on=VERIFIED_ON));changed+=1
    if changed:
        db.session.add(ComplaintAuditLog(actor_id=actor.id,action='PILA_CONTACT_IMPORT',details=f'User-requested import: {changed} official LGU-published contacts. Source checked 2026-10-09; telephone connectivity not tested.'))
    return changed
