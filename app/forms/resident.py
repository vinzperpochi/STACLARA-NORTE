"""Resident portal form validation classes."""

from datetime import date, datetime, time
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, DateField, DateTimeLocalField,
    TimeField, IntegerField, HiddenField
)
from wtforms.validators import (
    DataRequired, Length, Optional, NumberRange, ValidationError
)

from app.extensions import db
from app.models import Purok, DocumentType
from .common import (
    BaseForm, coerce_optional_int, validate_phone_number, validate_date_range, 
    validate_file_upload, sanitize_input
)


class CorrectionRequestForm(BaseForm):
    """Form for residents to request corrections to their personal data."""
    
    field_name = SelectField(
        'Field to Correct',
        validators=[
            DataRequired(message='Select the field you want to correct')
        ],
        render_kw={'class': 'form-select'}
    )
    
    current_value = StringField(
        'Current Value',
        validators=[Optional()],
        render_kw={
            'class': 'form-control',
            'readonly': True,
            'placeholder': 'Current value will appear here'
        }
    )
    
    proposed_value = StringField(
        'Proposed Correction',
        validators=[
            DataRequired(message='Enter the correct value'),
            Length(min=1, max=255, message='Correction must be 1-255 characters')
        ],
        render_kw={
            'placeholder': 'Enter the correct information',
            'class': 'form-control'
        }
    )
    
    reason = TextAreaField(
        'Reason for Correction',
        validators=[
            DataRequired(message='Explain why this correction is needed'),
            Length(min=10, max=500, message='Reason must be 10-500 characters')
        ],
        render_kw={
            'placeholder': 'Please explain why this information needs to be corrected',
            'class': 'form-control',
            'rows': 3,
            'maxlength': 500
        }
    )
    
    def __init__(self, resident=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Define correctable fields
        correctable_fields = {
            'first_name': 'First Name',
            'middle_name': 'Middle Name', 
            'last_name': 'Last Name',
            'birth_date': 'Birth Date',
            'sex': 'Sex',
            'civil_status': 'Civil Status',
            'occupation': 'Occupation',
            'contact_number': 'Contact Number',
            'email': 'Email Address',
            'address_line': 'Address',
            'voter_status': 'Voter Status'
        }
        
        self.field_name.choices = [('', 'Select field to correct')] + [
            (field, label) for field, label in correctable_fields.items()
        ]
        
        self.resident = resident
        today = date.today()
        try:
            youngest = today.replace(year=today.year-10)
        except ValueError:
            youngest = today.replace(year=today.year-10,day=28)
        self.proposed_value.render_kw.update({'data-correction-value':'true',
            'data-correction-date-min':'1970-01-01','data-correction-date-max':youngest.isoformat()})
    
    def validate_proposed_value(self, field):
        """Validate proposed value based on field type."""
        if not field.data or not self.field_name.data:
            return
        
        proposed = sanitize_input(field.data.strip())
        field_name = self.field_name.data
        
        # Field-specific validation
        if field_name == 'email':
            import re
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', proposed):
                raise ValidationError('Enter a valid email address')
        
        elif field_name == 'contact_number' and proposed:
            # Use existing phone validator
            try:
                validate_phone_number(None, type('Field', (), {'data': proposed})())
            except ValidationError as e:
                raise ValidationError(str(e))
        
        elif field_name == 'birth_date':
            try:
                birth_date = datetime.strptime(proposed, '%Y-%m-%d').date()
                if birth_date > date.today():
                    raise ValidationError('Birth date cannot be in the future')
                if birth_date < date(1970, 1, 1):
                    raise ValidationError('Birth date must be after January 1, 1970')
                # Check minimum age (10 years old)
                today = date.today()
                try:
                    youngest_allowed = today.replace(year=today.year - 10)
                except ValueError:
                    youngest_allowed = today.replace(year=today.year - 10, day=28)
                if birth_date > youngest_allowed:
                    raise ValidationError('Person must be at least 10 years old')
            except ValueError:
                raise ValidationError('Enter birth date in YYYY-MM-DD format')
        
        elif field_name in ['first_name', 'last_name', 'middle_name']:
            if not proposed.replace(' ', '').replace('-', '').replace('.', '').isalpha():
                raise ValidationError('Names can only contain letters, spaces, hyphens, and periods')
        
        field.data = proposed


class DocumentRequestForm(BaseForm):
    """Form for requesting official documents."""
    
    document_type_id = SelectField(
        'Document Type',
        coerce=coerce_optional_int,
        validators=[
            DataRequired(message='Select the document you need')
        ],
        render_kw={'class': 'form-select'}
    )
    
    description = TextAreaField(
        'Purpose/Description',
        validators=[
            Optional(),
            Length(max=500, message='Description cannot exceed 500 characters')
        ],
        render_kw={
            'placeholder': 'Optional: Specify the purpose or add special instructions',
            'class': 'form-control',
            'rows': 3,
            'maxlength': 500
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate document type choices
        self.document_type_id.choices = [('', 'Select document type')] + [
            (dt.id, f"{dt.name} - ₱{dt.base_fee:.2f}") 
            for dt in db.session.scalars(
                db.select(DocumentType)
                .where(DocumentType.status == 'active')
                .order_by(DocumentType.name)
            ).all()
        ]


class RequirementUploadForm(BaseForm):
    """Form for uploading document requirements."""
    
    requirement_file = FileField(
        'Requirement File',
        validators=[
            FileRequired(message='Please select a file to upload'),
            FileAllowed(['jpg', 'jpeg', 'png'], 
                       'Only JPEG and PNG images are allowed'),
            validate_file_upload(
                allowed_extensions=['jpg', 'jpeg', 'png'],
                max_size_mb=5
            )
        ],
        render_kw={
            'class': 'form-control',
            'accept': '.jpg,.jpeg,.png'
        }
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[
            Optional(),
            Length(max=255, message='Notes cannot exceed 255 characters')
        ],
        render_kw={
            'placeholder': 'Optional notes about this document',
            'class': 'form-control',
            'rows': 2,
            'maxlength': 255
        }
    )


class BlotterCaseForm(BaseForm):
    """Form for filing blotter cases/complaints."""
    
    incident_date = DateField(
        'Incident Date',
        validators=[
            DataRequired(message='Incident date is required'),
            validate_date_range(
                min_date=date(2020, 1, 1),
                max_date=date.today(),
                allow_future=False
            )
        ],
        render_kw={
            'class': 'form-control',
            'max': date.today().isoformat()
        }
    )
    
    incident_datetime = DateTimeLocalField(
        'Incident Time',
        validators=[Optional()],
        render_kw={
            'class': 'form-control'
        }
    )
    
    incident_location = StringField(
        'Location of Incident',
        validators=[
            Optional(),
            Length(max=255, message='Location cannot exceed 255 characters')
        ],
        render_kw={
            'placeholder': 'Where did the incident occur?',
            'class': 'form-control'
        }
    )
    
    incident_latitude = HiddenField('Incident Latitude')
    incident_longitude = HiddenField('Incident Longitude')
    
    purok_id = SelectField(
        'Purok',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    respondent_name = StringField(
        'Respondent Name',
        validators=[
            DataRequired(message='Respondent name is required'),
            Length(min=2, max=200, message='Respondent name must be 2-200 characters')
        ],
        render_kw={
            'placeholder': 'Name of the person being complained against',
            'class': 'form-control'
        }
    )
    
    respondent_contact = StringField(
        'Respondent Contact',
        validators=[
            Optional(),
            validate_phone_number
        ],
        render_kw={
            'placeholder': 'Contact number (if known)',
            'class': 'form-control'
        }
    )
    
    category = SelectField(
        'Category',
        validators=[
            DataRequired(message='Select the category of complaint')
        ],
        choices=[
            ('', 'Select category'),
            ('Noise complaint', 'Noise complaint'),
            ('Property dispute', 'Property dispute'),
            ('Harassment', 'Harassment'),
            ('Threat', 'Threat'),
            ('Vandalism', 'Vandalism'),
            ('Trespassing', 'Trespassing'),
            ('Debt collection', 'Debt collection'),
            ('Family dispute', 'Family dispute'),
            ('Business dispute', 'Business dispute'),
            ('Other', 'Other')
        ],
        render_kw={'class': 'form-select'}
    )
    
    narrative = TextAreaField(
        'Incident Narrative',
        validators=[
            DataRequired(message='Please describe what happened'),
            Length(min=20, max=2000, message='Narrative must be 20-2000 characters')
        ],
        render_kw={
            'placeholder': 'Describe the incident in detail. Include relevant facts, witnesses, and any evidence.',
            'class': 'form-control',
            'rows': 6,
            'maxlength': 2000
        }
    )
    
    respondent_notes = TextAreaField(
        'Additional Notes about Respondent',
        validators=[
            Optional(),
            Length(max=500, message='Notes cannot exceed 500 characters')
        ],
        render_kw={
            'placeholder': 'Additional information about the respondent (optional)',
            'class': 'form-control',
            'rows': 2,
            'maxlength': 500
        }
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate purok choices
        # coerce_optional_int converts the blank option to None, so the
        # blank choice must use None as its value as well.
        self.purok_id.choices = [(None, 'Select purok (if applicable)')] + [
            (p.id, p.name) for p in db.session.scalars(
                db.select(Purok).order_by(Purok.name)
            ).all()
        ]


class QueueRequestForm(BaseForm):
    """Form for joining service queues."""
    
    request_type = SelectField(
        'Service Type',
        validators=[
            DataRequired(message='Select the type of service you need')
        ],
        choices=[
            ('', 'Select service type'),
            ('DOCUMENT', 'Document Processing'),
            ('COMPLAINT', 'Complaint Filing'),
            ('APPOINTMENT', 'Official Appointment'),
            ('CONSULTATION', 'Consultation'),
            ('OTHER', 'Other Service')
        ],
        render_kw={'class': 'form-select'}
    )
    
    description = TextAreaField(
        'Service Description',
        validators=[
            DataRequired(message='Describe the service you need'),
            Length(min=10, max=500, message='Description must be 10-500 characters')
        ],
        render_kw={
            'placeholder': 'Please describe what service you need or what you want to discuss',
            'class': 'form-control',
            'rows': 3,
            'maxlength': 500
        }
    )
    
    appointment_date = DateField(
        'Preferred Date',
        validators=[
            Optional(),
            validate_date_range(
                min_date=date.today(),
                allow_future=True
            )
        ],
        render_kw={
            'class': 'form-control',
            'min': date.today().isoformat()
        }
    )
    
    appointment_time = TimeField(
        'Preferred Time',
        validators=[Optional()],
        render_kw={'class': 'form-control'}
    )
    
    priority_reason = TextAreaField(
        'Reason for Priority',
        validators=[
            Optional(),
            Length(max=255, message='Priority reason cannot exceed 255 characters')
        ],
        render_kw={
            'placeholder': 'Optional: Explain if you need priority service (senior, PWD, emergency, etc.)',
            'class': 'form-control',
            'rows': 2,
            'maxlength': 255
        }
    )
    
    def validate_appointment_time(self, field):
        """Validate appointment time is within office hours."""
        if field.data:
            # Assume office hours 8 AM to 5 PM
            if field.data < time(8, 0) or field.data > time(17, 0):
                raise ValidationError('Please select a time during office hours (8:00 AM - 5:00 PM)')
