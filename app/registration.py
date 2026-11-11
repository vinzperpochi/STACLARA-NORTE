"""Extended registration choices and transactional private file handling."""
from app.image_uploads import save_image, remove_image
from app.normalization import clean_text

EDUCATION = [('', 'Select educational attainment'), ('none', 'No formal education'), ('elementary', 'Elementary'), ('high_school', 'High school'), ('senior_high', 'Senior high school'), ('vocational', 'Vocational / technical'), ('college', 'College'), ('postgraduate', 'Postgraduate')]
RELATIONSHIPS = [('', 'Select relationship'), ('head', 'Household head'), ('spouse', 'Spouse / partner'), ('child', 'Child'), ('parent', 'Parent'), ('sibling', 'Sibling'), ('grandparent', 'Grandparent'), ('grandchild', 'Grandchild'), ('relative', 'Other relative'), ('non_relative', 'Non-relative')]
DURATIONS = [('', 'Select duration'), ('less_than_1', 'Less than 1 year'), ('1_to_3', '1–3 years'), ('4_to_5', '4–5 years'), ('6_to_10', '6–10 years'), ('over_10', 'More than 10 years'), ('since_birth', 'Since birth')]
CATEGORIES = [('senior', 'Senior Citizen'), ('pwd', 'Person with Disability'), ('4ps', '4Ps Beneficiary'), ('solo_parent', 'Solo Parent'), ('first_time_jobseeker', 'First-Time Jobseeker'), ('registered_voter', 'New / Active Registered Voter')]
PROFILE_FIELDS = ['place_of_birth', 'religion', 'educational_attainment', 'household_relationship', 'house_no', 'street_landmark', 'residency_duration', 'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_number']
FILES = {'proof': 'proof_of_residency_filename', 'philsys': 'philsys_card_filename'}
PROFILE_CORRECTION_FIELDS = PROFILE_FIELDS + ['nationality', 'special_categories']


def correction_text(value):
    import json
    return json.dumps(sorted(value), ensure_ascii=False) if isinstance(value, list) else str(value or '')


def parse_correction(resident, name, proposed):
    """Validate and restore the real type before approving a resident change."""
    import json
    from app.forms.official import ResidentForm
    allowed = set(PROFILE_CORRECTION_FIELDS) | {'first_name','middle_name','last_name','birth_date',
        'sex','civil_status','occupation','contact_number','email','address_line','voter_status'}
    if name not in allowed:
        raise ValueError('This field cannot be changed through a correction request.')
    form = ResidentForm(formdata=None, obj=resident, meta={'csrf':False})
    field = form[name]
    try:
        values = json.loads(proposed) if name == 'special_categories' else [proposed]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError('Invalid category selection.')
        field.process_formdata(values)
        if not field.validate(form):
            raise ValueError(' '.join(field.errors))
        if name == 'special_categories':
            form.validate_special_categories(field)
        value = field.data
        if name == 'nationality' and not value:
            raise ValueError('Nationality cannot be empty.')
        return clean_text(value) if isinstance(value, str) and value else value or ([] if name=='special_categories' else None)
    except (TypeError, ValueError) as error:
        raise ValueError(str(error)) from error

def apply_profile(form, resident, user, created_files):
    for name in PROFILE_FIELDS:
        value = getattr(form, name).data
        setattr(resident, name, clean_text(value) if value else None)
    resident.special_categories = list(form.special_categories.data or [])
    if resident.house_no or resident.street_landmark:
        resident.address_line = ', '.join(v for v in [resident.house_no, resident.street_landmark] if v)
    store_profile_uploads(form, resident, created_files, user)


def store_profile_uploads(form, resident, created_files, user=None):
    """Track each new upload so callers can clean files after a rolled-back save."""
    for name, column in [('proof_of_residency', 'proof_of_residency_filename'), ('philsys_card', 'philsys_card_filename')]:
        file = getattr(form, name).data
        if file and file.filename:
            try:
                filename = save_image(file, 'registration_documents')
            except ValueError as error:
                getattr(form, name).errors.append(str(error))
                raise
            created_files.append(('registration_documents', filename))
            setattr(resident, column, filename)
    file = form.profile_photo.data
    if file and file.filename:
        try:
            filename = save_image(file, 'profile_photos')
        except ValueError as error:
            form.profile_photo.errors.append(str(error))
            raise
        created_files.append(('profile_photos', filename))
        resident.profile_photo_filename = filename
        account = user if user is not None else resident.user
        if account is not None:
            account.profile_photo_filename = filename


def profile_upload_snapshot(resident):
    return [('profile_photos', resident.profile_photo_filename),
            ('registration_documents', resident.proof_of_residency_filename),
            ('registration_documents', resident.philsys_card_filename)]


def cleanup_replaced_uploads(before, resident):
    current = set(profile_upload_snapshot(resident))
    cleanup_files([entry for entry in before if entry not in current])

def cleanup_files(files):
    for folder, filename in files:
        remove_image(folder, filename)


def send_registration_file(resident, kind):
    from pathlib import Path
    from flask import current_app, abort, send_from_directory
    from app.extensions import db
    from app.audit import record
    column = FILES.get(kind)
    if not column:
        abort(404)
    filename = getattr(resident, column)
    if not filename or Path(filename).name != filename or Path(filename).suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
        abort(404)
    from app.private_storage import private_image_path
    image_path = private_image_path('registration_documents',filename)
    if image_path is None:
        abort(404)
    record('REGISTRATION_FILE_VIEW', 'registration', 'Resident', resident.id, 'Private registration verification image viewed')
    db.session.commit()
    response=send_from_directory(image_path.parent,image_path.name)
    response.headers['Cache-Control']='private, no-store'
    return response
