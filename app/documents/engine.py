"""Bind verified data into the fourteen supplied A4 Jinja templates."""
from __future__ import annotations
import calendar
import hashlib
import json
import os
import re
import math
from xml.sax.saxutils import escape as xml_escape
import shutil
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from uuid import uuid4
from flask import current_app, render_template
from sqlalchemy import or_, select
from app.extensions import db
from app.models import DocumentSequence, DocumentSignatory, FeeConfiguration

TEMPLATE_CODES = {'CERTIFICATE_INDIGENCY':'SCN-IND','CERTIFICATE_RESIDENCY':'SCN-RSD','BUSINESS_CLEARANCE':'SCN-BIZ','BARANGAY_CLEARANCE':'SCN-CLR','CERTIFICATE_GOOD_MORAL':'SCN-GMC','SOLO_PARENT_ENDORSEMENT':'SCN-SPE','FIRST_TIME_JOBSEEKER':'SCN-FTJ'}
COMMON_FIELDS = {'valid_id':'Valid ID type and number'}
DETAIL_FIELDS = {
 'SCN-IND':{'monthly_income':'Estimated monthly family income (PHP)','dependents':'Dependents / household members','benefit_id':'4Ps / PWD / Senior ID (optional)'},
 'SCN-RSD':{'residency_since':'Residency start year','previous_address':'Previous address (if less than five years)','tenure':'Owner / renter / living with relatives','household_head':'Household head'},
 'SCN-BIZ':{'business_name':'Business / trade name','application_type':'Application type (New or Renewal)','business_nature':'Nature of business','business_area':'Business area (sq.m.)','employees':'Number of employees','business_address':'Business street / purok','business_registration':'DTI / SEC / CDA registration number','capital':'Capital (PHP)'},
 'SCN-CLR':{'cedula_number':'Community Tax Certificate number','cedula_issued':'Cedula issuance date and place'},
 'SCN-GMC':{'requesting_agency':'Requesting agency / institution'},
 'SCN-SPE':{'monthly_income':'Monthly income (PHP)','solo_reason':'Reason for being a solo parent',**{f'child_{i}_{k}':f'Child {i} {label}' for i in range(1,5) for k,label in [('name','name'),('birth_date','date of birth (YYYY-MM-DD)'),('relationship','relationship')]}},
 'SCN-FTJ':{'school_graduated':'School and year graduated'},
}
OPTIONAL = {'benefit_id','previous_address','household_head'} | {f'child_{i}_{k}' for i in range(2,5) for k in ['name','birth_date','relationship']}
CHECKLISTS = {
 'SCN-IND':['Indigency and family income verified against supporting records'],
 'SCN-RSD':['Residency start date and continuous residency verified'],
 'SCN-BIZ':['Registration, premises, ownership and business details verified'],
 'SCN-CLR':['Barangay justice and derogatory records checked: no pending or adverse record'],
 'SCN-GMC':['Good moral character and barangay records verified: no derogatory record'],
 'SCN-SPE':['Solo parent eligibility and each child verified against supporting records'],
 'SCN-FTJ':['First time jobseeker: never employed and has not availed this benefit before','Signed oath executed in the presence of a barangay official verified'],
}

def template_code(document_type):
    code=document_type.template_code or TEMPLATE_CODES.get(document_type.code,document_type.code)
    if code not in DETAIL_FIELDS: raise ValueError('This document type has no approved original template mapping.')
    return code

def age_at(birth,issued):
    return issued.year-birth.year-((issued.month,issued.day)<(birth.month,birth.day))

def barangay_today():
    return datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Manila')).date()

def local_day(timestamp):
    if timestamp.tzinfo is None: timestamp=timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(ZoneInfo('Asia/Manila')).date()

def add_months(day,months):
    year=day.year+(day.month-1+months)//12;month=(day.month-1+months)%12+1
    return day.replace(year=year,month=month,day=min(day.day,calendar.monthrange(year,month)[1]))

def expiry(code,issued):
    return date(issued.year,12,31) if code=='SCN-BIZ' else add_months(issued,12 if code in {'SCN-SPE','SCN-FTJ'} else 6)

def resident_data(resident,issued=None):
    issued=issued or barangay_today()
    local=resident.address_line or ', '.join(filter(None,[resident.house_no,resident.street_landmark]))
    for suffix in [', Barangay Sta. Clara Norte, Pila, Laguna',', Sta. Clara Norte, Pila, Laguna']:
        if local.casefold().endswith(suffix.casefold()): local=local[:-len(suffix)]
    if resident.purok and resident.purok.name.casefold() not in local.casefold(): local=', '.join(filter(None,[local,resident.purok.name]))
    household_head=''
    if resident.household and resident.household.head_resident:
        h=resident.household.head_resident;household_head=' '.join(filter(None,[h.first_name,h.middle_name,h.last_name,h.suffix]))
    duration=resident.residency_duration or ''
    try: exact_years=duration if Decimal(duration).is_finite() and Decimal(duration)>=0 else ''
    except Exception: exact_years=''
    return dict(first_name=resident.first_name,last_name=resident.last_name,middle_name=resident.middle_name or '',suffix=resident.suffix or '',full_name=' '.join(filter(None,[resident.first_name,resident.middle_name,resident.last_name,resident.suffix])),birth_date=resident.birth_date.strftime('%m/%d/%Y') if resident.birth_date else '',age=str(age_at(resident.birth_date,issued)) if resident.birth_date else '',sex=resident.sex or '',civil_status=resident.civil_status or '',citizenship=resident.nationality or '',local_address=local,complete_address=', '.join(filter(None,[local,'Barangay Sta. Clara Norte, Pila, Laguna'])),barangay='Sta. Clara Norte / Pila, Laguna',contact_number=resident.contact_number or '',email=resident.email or (resident.user.email if resident.user else ''),residency_years=exact_years,residency_summary=duration if not exact_years else '',resident_id=str(resident.id),occupation=resident.occupation or '',education=resident.educational_attainment or '',household_head=household_head)

def fields_for(resident,code):
    data=resident_data(resident)
    # Resident fields already present are readonly; corrections use the existing profile correction workflow.
    fields=dict(COMMON_FIELDS)
    for key,label in {'birth_date':'Date of birth (YYYY-MM-DD)','sex':'Sex','civil_status':'Civil status','citizenship':'Citizenship','local_address':'House / street / purok','contact_number':'Contact number','residency_years':'Years of residency','occupation':'Occupation','education':'Educational attainment'}.items():
        if key=='education' and code!='SCN-FTJ': continue
        if key=='occupation' and code in {'SCN-BIZ','SCN-FTJ'}: continue
        if not data[key]: fields[key]=label
    fields.update({k:v for k,v in DETAIL_FIELDS[code].items() if not data.get(k)})
    return fields

def validate_details(resident,code,form):
    values={}
    for key,label in fields_for(resident,code).items():
        value=form.get('detail_'+key,'').strip()
        limit=100 if key.startswith('child_') and key.endswith('_name') else 40 if key.endswith('_relationship') else 250
        if len(value)>limit: raise ValueError(label+f' must not exceed {limit} characters.')
        if not value and key not in OPTIONAL: raise ValueError(label+' is required.')
        values[key]=value
    for key in ['birth_date']+[f'child_{i}_birth_date' for i in range(1,5)]:
        if values.get(key):
            try: parsed=date.fromisoformat(values[key])
            except ValueError: raise ValueError('Enter a valid date for '+key.replace('_',' '))
            if parsed>barangay_today(): raise ValueError('Date of birth cannot be in the future.')
    for key in ['monthly_income','dependents','business_area','employees','capital','residency_years','residency_since']:
        if values.get(key):
            try: n=Decimal(values[key])
            except Exception: raise ValueError('Enter a number for '+key.replace('_',' '))
            if not n.is_finite() or n<0 or n>999999999: raise ValueError('Invalid amount for '+key.replace('_',' '))
            if key in {'dependents','employees','residency_since'} and n!=int(n): raise ValueError(key+' must be a whole number.')
    if code=='SCN-RSD' and int(values['residency_since'])>barangay_today().year: raise ValueError('Residency start year cannot be in the future.')
    if code=='SCN-BIZ' and values.get('application_type') not in {'New','Renewal'}: raise ValueError('Application type must be New or Renewal.')
    for i in range(1,5):
        child=[values.get(f'child_{i}_{k}') for k in ['name','birth_date','relationship']]
        if any(child) and not all(child): raise ValueError('Complete all three fields for child '+str(i))
    return values

def active_signatories(day=None):
    day=day or barangay_today()
    return db.session.scalars(select(DocumentSignatory).where(DocumentSignatory.status=='active',DocumentSignatory.effective_from<=day,or_(DocumentSignatory.effective_until.is_(None),DocumentSignatory.effective_until>=day))).all()

def configured_fee(document_type,day):
    if template_code(document_type)=='SCN-FTJ': return Decimal('0')
    fee=db.session.scalar(select(FeeConfiguration).where(FeeConfiguration.document_type_id==document_type.id,FeeConfiguration.status=='active',FeeConfiguration.effective_from<=day,or_(FeeConfiguration.effective_until.is_(None),FeeConfiguration.effective_until>=day)).order_by(FeeConfiguration.effective_from.desc(),FeeConfiguration.id.desc()))
    return Decimal(str(fee.amount if fee else document_type.base_fee))

def fee_confirmed(document_type,day):
    if template_code(document_type)=='SCN-FTJ' or document_type.base_fee>0: return True
    return db.session.scalar(select(FeeConfiguration.id).where(FeeConfiguration.document_type_id==document_type.id,FeeConfiguration.status=='active',FeeConfiguration.effective_from<=day,or_(FeeConfiguration.effective_until.is_(None),FeeConfiguration.effective_until>=day))) is not None

def verification_digest(item):
    identity=resident_data(item.resident)
    identity.pop('age',None)
    payload=dict(identity=identity,details=item.additional_data or {},purpose=item.description,requirements=[(r.id,r.filename,r.status,r.is_required) for r in item.requirements],signatory=(item.signatory.id,item.signatory.full_name,item.signatory.designation) if item.signatory else None,fee=str(configured_fee(item.document_type,barangay_today())),template=template_code(item.document_type))
    from .workflow import evidence_source
    reused = [(r.id, evidence_source(r)[1]) for r in item.active_requirements if not r.filename and evidence_source(r)[1]]
    if reused: payload['registration_evidence'] = reused
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def next_number(code,year):
    """Atomic upsert/update; numbering and issuance commit in one transaction."""
    dialect=db.session.get_bind().dialect.name
    if dialect=='postgresql': from sqlalchemy.dialects.postgresql import insert
    elif dialect=='sqlite': from sqlalchemy.dialects.sqlite import insert
    else: raise ValueError('Control numbering requires the configured PostgreSQL database.')
    now=datetime.now(timezone.utc)
    statement=insert(DocumentSequence).values(template_code=code,year=year,last_number=1,created_at=now,updated_at=now)
    statement=statement.on_conflict_do_update(index_elements=['template_code','year'],set_={'last_number':DocumentSequence.last_number+1,'updated_at':now}).returning(DocumentSequence.last_number)
    serial=db.session.execute(statement).scalar_one()
    return f'{code}-{year}-{serial:06d}'

def snapshot_data(item,document,*,allow_pending_payment=False):
    day=document.issued_at.date();code=template_code(item.document_type)
    data=resident_data(item.resident,day)
    # Only previously missing values can supplement registered identity.
    for key,value in (item.additional_data or {}).items():
        if key not in data or not data[key]: data[key]=value
    if not item.resident.birth_date and data.get('birth_date'):
        birth=date.fromisoformat(data['birth_date']);data['age']=str(age_at(birth,day));data['birth_date']=birth.strftime('%m/%d/%Y')
    if not data['local_address']: raise ValueError('Verified residential address is required.')
    data['complete_address']=data['local_address']+', Barangay Sta. Clara Norte, Pila, Laguna'
    received=next((e for e in item.status_history if e.to_status=='UNDER_REVIEW'),None)
    received_user=received.changed_by if received else None
    received_name=(received_user.official.full_name if received_user and received_user.official else received_user.username) if received_user else ''
    verifier=item.verified_by
    verified_name=(verifier.official.full_name if verifier.official else verifier.username) if verifier else ''
    data.update(year=str(day.year),serial=document.document_number.rsplit('-',1)[1],control_number=document.document_number,date_issued=day.strftime('%m/%d/%Y'),day=str(day.day),month=day.strftime('%B'),purpose=item.description or '',valid_until=document.expires_at.strftime('%m/%d/%Y'),fee=f'{configured_fee(item.document_type,day):.2f}',signatory_name=item.signatory.full_name,signatory_designation=item.signatory.designation,qr_uri=document.qr_code_data_uri,office_phone=current_app.config.get('BARANGAY_CONTACT_PHONE',''),office_email=current_app.config.get('BARANGAY_CONTACT_EMAIL',''),received_by=received_name,date_received=local_day(received.created_at if received else item.created_at).strftime('%m/%d/%Y'),verified_by=verified_name,review_notes=item.verification_notes or '')
    payments=[p for p in item.payments if p.status=='paid']
    paid=sum((Decimal(str(p.amount)) for p in payments),Decimal(0))
    if not allow_pending_payment and paid<Decimal(data['fee']): raise ValueError('Record the required payment and official receipt before issuance.')
    receipt=payments[-1] if payments else None
    data.update(receipt_number=receipt.receipt_number if receipt else 'N/A',receipt_date=local_day(receipt.paid_at).strftime('%m/%d/%Y') if receipt else 'N/A',receipt_combined=(receipt.receipt_number+' / '+local_day(receipt.paid_at).strftime('%m/%d/%Y')) if receipt else 'N/A')
    if allow_pending_payment:
        confirmed=fee_confirmed(item.document_type,day)
        data['payment_pending']=not confirmed or paid<configured_fee(item.document_type,day)
        data['fee']=f'{paid:.2f}' if receipt else ('0.00' if confirmed and configured_fee(item.document_type,day)==0 else '')
        if not receipt:
            data.update(receipt_number='',receipt_date='',receipt_combined='')
    children=[]
    for i in range(1,5):
        name=data.get(f'child_{i}_name','');birth=data.get(f'child_{i}_birth_date','')
        children.append(dict(name=name,age=str(age_at(date.fromisoformat(birth),day)) if birth else '',birth_date=date.fromisoformat(birth).strftime('%m/%d/%Y') if birth else '',relationship=data.get(f'child_{i}_relationship','')))
        data[f'child_{i}']=' / '.join(filter(None,[name,children[-1]['age'],children[-1]['birth_date']]))
    data['children']=children
    data['long_fields']=len(data['full_name'])>65 or len(data['local_address'])>100 or len(data['purpose'])>150 or any(len(c['name'])>45 for c in children)
    if len(data['review_notes'])>140: data['review_notes']='See verified review findings in request '+item.request_number
    return data

def render_original(code,data,kind='certificate'):
    if code not in DETAIL_FIELDS or kind not in {'certificate','application'}: raise ValueError('Unknown official template.')
    data=dict(data)
    data.setdefault('long_fields',len(data.get('full_name',''))>65 or len(data.get('local_address',''))>100 or len(data.get('purpose',''))>150)
    return render_template(f'documents/original/{code}-{kind}.html',data=data,title=code,application_grid=application_grid)

def application_grid(data,layout,width=482.5):
    """Reserve actual text height in the original twelve-column form grid."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name='SCNApplicationSans'
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name,str(Path(current_app.root_path)/'static/fonts/document-original/LiberationSans-Regular.ttf')))
    font_size=6.5 if data.get('long_fields') else 7
    rows=[];slots=0;row_height=23.24
    def lines(text,available,size):
        if not text: return 1
        count=1;line=''
        for word in str(text).split():
            if pdfmetrics.stringWidth((line+' '+word).strip(),name,size)<=available: line=(line+' '+word).strip()
            else:
                if line: count+=1
                word_width=pdfmetrics.stringWidth(word,name,size)
                count+=max(0,math.ceil(word_width/available)-1)
                line=word
        return count
    for field in layout:
        span=field['span']
        if slots+span>12: rows.append(row_height);slots=0;row_height=23.24
        available=(width-11*8.504)/12*span+(span-1)*8.504
        label_height=lines(field['label'].upper(),available,6.8)*7.48
        value_height=max(15.88,lines(data.get(field['key'],''),available,font_size)*font_size*1.15+2.83)
        row_height=max(row_height,label_height+value_height)
        slots+=span
        if slots==12: rows.append(row_height);slots=0;row_height=23.24
    if slots: rows.append(row_height)
    return 'grid-template-rows:'+' '.join(f'{h:.2f}pt' for h in rows)

def chromium_path():
    candidates=[current_app.config.get('DOCUMENT_PDF_BROWSER'),os.environ.get('DOCUMENT_PDF_BROWSER'),shutil.which('chromium'),shutil.which('chromium-browser'),shutil.which('google-chrome'),r'C:\Program Files\Google\Chrome\Application\chrome.exe',r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe']
    for candidate in candidates:
        if candidate and Path(candidate).is_file(): return str(candidate)
    raise ValueError('PDF renderer unavailable. Install Chrome/Chromium or set DOCUMENT_PDF_BROWSER.')

def pdf_bytes(content):
    """Render local, embedded-asset original HTML to A4 without external requests."""
    directory=(Path(current_app.config['STORAGE_ROOT'])/'generated_documents').resolve()
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/('render-'+uuid4().hex)
    path.mkdir()
    try:
        html=path/'certificate.html';pdf=path/'certificate.pdf';html.write_text(content,encoding='utf-8')
        renderer=current_app.config.get('DOCUMENT_PDF_RENDERER') or os.environ.get('DOCUMENT_PDF_RENDERER')
        bundled=Path(current_app.root_path).parent/'tools/pdf-runtime/onedir/weasyprint/weasyprint.exe'
        renderer=renderer or (str(bundled) if os.name=='nt' and bundled.is_file() else shutil.which('weasyprint'))
        if renderer:
            # Fontconfig reads the supplied font files directly. This avoids
            # platform font substitutions and temporary font-file ACL problems.
            html.write_text(re.sub(r'@font-face\{[^}]*\}', '', content),encoding='utf-8')
            font_dir=Path(current_app.root_path)/'static/fonts/document-original'
            cache=directory/'font-cache';cache.mkdir(exist_ok=True)
            config=path/'fonts.conf'
            system_fonts='<dir>C:/Windows/Fonts</dir>' if os.name=='nt' else '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
            config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>'+xml_escape(font_dir.as_posix())+'</dir>'+system_fonts+'<cachedir>'+xml_escape(cache.as_posix())+'</cachedir></fontconfig>',encoding='utf-8')
            environment=os.environ.copy();environment['FONTCONFIG_FILE']=str(config)
            command=[renderer,str(html),str(pdf)]
        else:
            environment=os.environ.copy()
            command=[chromium_path(),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions','--no-pdf-header-footer','--run-all-compositor-stages-before-draw','--user-data-dir='+str(path/'profile'),'--print-to-pdf='+str(pdf),html.as_uri()]
        try: subprocess.run(command,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,check=True)
        except (OSError,subprocess.SubprocessError) as error: raise ValueError('Could not render the official PDF. Check DOCUMENT_PDF_RENDERER or DOCUMENT_PDF_BROWSER.') from error
        if not pdf.is_file(): raise ValueError('PDF renderer did not produce a document.')
        return pdf.read_bytes()
    finally:
        # Keep the inherited private-storage ACL on Windows (mkdtemp's 0700 ACL
        # can exclude the managed runtime account). Only remove our checked child.
        if path.resolve().parent==directory:
            shutil.rmtree(path,ignore_errors=True)
