import csv
from io import StringIO
from datetime import date,datetime,timezone
import pytest
from app.extensions import db
from app.models import User,Purok,Household,HealthRegistry,DocumentType,IssuedDocument,Request,BlotterCase,DRRMIncident
from app.models.phase9 import BeneficiaryRegistry
from app.models.phase12 import CollectionEntry
from app.admin import REPORT_CATALOG
from test_system_integrity import system,login

@pytest.fixture
def report_data(system):
    stamp=datetime(2025,1,15,12,tzinfo=timezone.utc)
    resident=db.session.scalar(db.select(User).where(User.username=='resident-test')).resident
    resident.created_at=stamp;resident.last_name='=Formula';resident.sex='Female'
    p=Purok(name='Purok 7',created_at=stamp)
    h=Household(household_number='REPORT-HH',address_line='QA address',purok=p,created_at=stamp)
    resident.purok=p;resident.household=h
    dt=DocumentType(code='REPORT',name='QA Certificate')
    entries=[p,h,dt,
        HealthRegistry(resident=resident,created_at=stamp,medical_conditions='<test> '+('Long medical note ' * 80)),
        BeneficiaryRegistry(resident=resident,category='SENIOR',registered_date=date(2025,1,15)),
        Request(request_number='REPORT-REQ',resident=resident,document_type=dt,service_type='QA Certificate',created_at=stamp),
        IssuedDocument(document_number='REPORT-DOC',resident=resident,document_type=dt,issued_at=stamp,created_at=datetime(2020,1,1,tzinfo=timezone.utc),authorized_signatory='QA official',verification_url='https://example.com/qa',qr_code_data_uri='qa'),
        BlotterCase(case_number='REPORT-CASE',complainant=resident,respondent_name='QA respondent',incident_date=date(2025,1,15),incident_location='QA location',narrative='QA narrative'),
        CollectionEntry(transaction_number='REPORT-PAY',resident=resident,service='QA service',amount=100,payment_method='Cash',transaction_date=date(2025,1,15)),
        DRRMIncident(title='QA incident',incident_type='Flood',incident_date=date(2025,1,15),started_at=stamp,damage_assessment='QA long note '*80)]
    db.session.add_all(entries);db.session.commit()
    return system

@pytest.mark.parametrize('username,base,center',[('admin-test','/admin/reports','/admin/reports'),('staff-test','/official/report-center','/official/report-center')])
def test_all_report_buttons_formats_filters_and_nonempty_rows(report_data,username,base,center):
    client=login(report_data,username)
    html=client.get(center).get_data(as_text=True)
    assert f'action="{base}/export"' in html
    assert 'onclick=' not in html
    assert 'name="start"' in html and 'name="end"' in html
    for kind in REPORT_CATALOG:
        assert f'formaction="{base}/export/{kind}/pdf"' in html
        for format in ['csv','pdf']:
            response=client.get(base+'/export',query_string={'kind':kind,'format':format,'start':'2025-01-15','end':'2025-01-15'})
            assert response.status_code==200,(kind,format)
            assert 'attachment' in response.headers['Content-Disposition']
            if format=='csv':
                rows=list(csv.reader(StringIO(response.data.decode('utf-8-sig'))))
                assert len(rows)==2,(kind,rows)
                if kind=='residents':assert rows[1][1].startswith("'=Formula")
            else:assert response.data.startswith(b'%PDF')
            response.close()
        empty=client.get(base+'/export',query_string={'kind':kind,'format':'csv','start':'2050-01-01'})
        assert len(list(csv.reader(StringIO(empty.data.decode('utf-8-sig')))))==1,kind
    assert client.get(base+'/export?kind=unknown&format=csv').status_code==404
    assert client.get(base+'/export?kind=residents&format=unknown').status_code==404
    assert client.get(base+'/export?kind=residents&start=bad').location.endswith(center)
    assert client.get(base+'/export?kind=residents&start=2025-02-01&end=2025-01-01').location.endswith(center)

@pytest.mark.parametrize('path',['/admin/reports/export','/official/report-center/export'])
def test_form_download_routes_deny_residents_and_anonymous(system,path):
    assert system.test_client().get(path+'?kind=residents').status_code==302
    assert login(system).get(path+'?kind=residents').status_code==403
