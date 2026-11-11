"""Public barangay information shared by help, privacy and portal views."""
from flask import current_app, g, has_request_context, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import SystemSetting

PSA_SOURCE = 'https://psa.gov.ph/classification/psgc/barangays/0403422000'
MUNICIPAL_SOURCE = 'https://elgu-pila-laguna-news.e.gov.ph/CONTACTUS'

FIELD_GROUPS = [
    ('Barangay profile', [('barangay_name','Barangay name'),('municipality','Municipality'),
        ('province','Province'),('country','Country'),('zip_code','Postal code')]),
    ('Barangay office & contacts', [('hall_address','Exact barangay hall address'),
        ('contact_phone','Barangay office phone / hotline'),('contact_email','Barangay office email'),
        ('office_hours','Confirmed office hours')]),
    ('Designated Data Protection Officer', [('dpo_name','Official DPO name'),
        ('dpo_email','Official DPO email'),('dpo_phone','Official DPO phone')]),
    ('Public assistance information', [('help_note','Walk-in assistance'),
        ('charter_note',"Citizen’s Charter information"),('fees_note','Service-fee information'),
        ('foi_note','Information-request instructions')]),
]
PUBLIC_FIELDS = {key:label for _,fields in FIELD_GROUPS for key,label in fields}
DEFAULTS = {
    'barangay_name':'Barangay Sta. Clara Norte','municipality':'Pila','province':'Laguna',
    'country':'Philippines','zip_code':'4010','psgc_code':'0403422016',
    'help_note':'Visit the barangay hall for walk-in assistance. Bring a valid government-issued ID and supporting documents relevant to your request.',
    'charter_note':'Ask the barangay office for the current Citizen’s Charter, service requirements, processing times, and fees.',
    'fees_note':'Service fees depend on the requested document and the current barangay fee schedule. Confirm the amount before payment.',
    'foi_note':'For requests for barangay information, ask the barangay office for the receiving officer and submission requirements.',
}
CONFIG_KEYS = {
    'barangay_name':'BARANGAY_NAME','contact_phone':'BARANGAY_CONTACT_PHONE',
    'contact_email':'BARANGAY_CONTACT_EMAIL','hall_address':'BARANGAY_HALL_ADDRESS',
    'office_hours':'BARANGAY_OFFICE_HOURS','dpo_name':'DPO_NAME','dpo_email':'DPO_EMAIL','dpo_phone':'DPO_PHONE',
}
ALIASES = {key:[key,key.upper(),CONFIG_KEYS.get(key,''),f'site.{key}'] for key in PUBLIC_FIELDS}
ALIASES['contact_phone'].insert(0,'hotline')
ALIASES['hall_address'].insert(0,'barangay_hall_address')


def public_information():
    if has_request_context() and getattr(g,'barangay_public_info_request',None) is request._get_current_object():
        return g.barangay_public_info
    values = {key:DEFAULTS.get(key,'') for key in PUBLIC_FIELDS}
    values['psgc_code'] = DEFAULTS['psgc_code']
    for key,config_key in CONFIG_KEYS.items():
        configured = current_app.config.get(config_key,'')
        if isinstance(configured,str) and configured.strip(): values[key] = configured.strip()
    try:
        allowed = {alias for aliases in ALIASES.values() for alias in aliases if alias}
        with db.session.no_autoflush:
            rows = db.session.scalars(db.select(SystemSetting).where(
                SystemSetting.setting_key.in_(allowed),SystemSetting.is_secret.is_(False))).all()
        configured = {row.setting_key:row.setting_value.strip() for row in rows}
        for key,aliases in ALIASES.items():
            for alias in aliases:
                if alias in configured: values[key] = configured[alias]
    except SQLAlchemyError:
        # Public informational pages remain readable during database outages.
        current_app.logger.warning('Public barangay information lookup unavailable')
    if has_request_context():
        g.barangay_public_info = values
        g.barangay_public_info_request = request._get_current_object()
    return values


def site_info_value(key):
    return public_information().get(key) or 'Kumpirmahin sa barangay hall.'


def save_public_information(form):
    """Save only the public fields explicitly shown in the administrator form."""
    for key,label in PUBLIC_FIELDS.items():
        value = (form[key].data or '').strip()
        row = db.session.scalar(db.select(SystemSetting).where(SystemSetting.setting_key==f'site.{key}'))
        if row and row.is_secret and not value:
            continue
        if row is None:
            row = SystemSetting(setting_key=f'site.{key}')
            db.session.add(row)
        row.setting_value = value
        row.description = f'Public barangay information: {label}'
        row.is_secret = False
