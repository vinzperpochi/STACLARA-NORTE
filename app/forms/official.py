"""Official portal form validation classes."""

from datetime import date, datetime, time
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, DateField, DateTimeLocalField,
    TimeField, IntegerField, FloatField, HiddenField, BooleanField
)
from wtforms.validators import (
    DataRequired, Length, Optional, NumberRange, ValidationError
)

from app.extensions import db
from app.models import Purok, Resident, DocumentType, User
from .common import (
    BaseForm, coerce_optional_int, validate_phone_number, validate_email_format, 
    validate_date_range, validate_person_name, validate_currency_amount, sanitize_input
)


from .profile_details import ProfileDetailsForm


class ResidentForm(ProfileDetailsForm):
    """Form for creating/editing resident records."""
    
    first_name = StringField(
        'First Name',
        validators=[
            DataRequired(message='First name is required'),
            Length(min=2, max=100, message='First name must be 2-100 characters'),
            validate_person_name,
        ],
        render_kw={'class': 'form-control', 'pattern': '[a-zA-Z\\s\\-\\.]+'}
    )
    
    middle_name = StringField(
        'Middle Name',
        validators=[Optional(), Length(max=100), validate_person_name],
        render_kw={'class': 'form-control', 'pattern': '[a-zA-Z\\s\\-\\.]*'}
    )
    
    last_name = StringField(
        'Last Name',
        validators=[
            DataRequired(message='Last name is required'),
            Length(min=2, max=100, message='Last name must be 2-100 characters'),
            validate_person_name,
        ],
        render_kw={'class': 'form-control', 'pattern': '[a-zA-Z\\s\\-\\.]+'}
    )
    
    suffix = StringField(
        'Suffix',
        validators=[Optional(), Length(max=20)],
        render_kw={'class': 'form-control'}
    )
    
    sex = SelectField(
        'Sex',
        choices=[('', 'Select sex'), ('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')],
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    birth_date = DateField(
        'Birth Date',
        validators=[
            Optional(),
            validate_date_range(min_date=date(1900, 1, 1), allow_future=False)
        ],
        render_kw={'class': 'form-control'}
    )
    
    civil_status = SelectField(
        'Civil Status',
        choices=[
            ('', 'Select civil status'),
            ('Single', 'Single'),
            ('Married', 'Married'),
            ('Widowed', 'Widowed'),
            ('Divorced', 'Divorced'),
            ('Separated', 'Separated')
        ],
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    occupation = StringField(
        'Occupation',
        validators=[Optional(), Length(max=150)],
        render_kw={'class': 'form-control'}
    )
    
    contact_number = StringField(
        'Contact Number',
        validators=[Optional(), validate_phone_number],
        render_kw={'class': 'form-control'}
    )
    
    email = StringField(
        'Email',
        validators=[Optional(), validate_email_format, Length(max=255)],
        render_kw={'class': 'form-control'}
    )
    
    address_line = StringField(
        'Address',
        validators=[Optional(), Length(max=255)],
        render_kw={'class': 'form-control'}
    )
    
    voter_status = SelectField(
        'Voter Status',
        choices=[
            ('unknown', 'Unknown'),
            ('registered', 'Registered'),
            ('not_registered', 'Not Registered'),
            ('pending', 'Pending Registration')
        ],
        default='unknown',
        render_kw={'class': 'form-select'}
    )
    
    purok_id = SelectField(
        'Purok',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    household_id = SelectField(
        'Household',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    household_member_no = IntegerField(
        'Household Member No.',
        validators=[Optional(), NumberRange(min=1, max=50)],
        render_kw={'class': 'form-control'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        from app.models import Household
        self.household_id.choices = [(None, 'Unassigned')] + [(h.id, h.household_number) for h in db.session.scalars(db.select(Household).order_by(Household.household_number)).all()]
        # Populate choices
        self.purok_id.choices = [('', 'Select purok')] + [
            (p.id, p.name) for p in db.session.scalars(
                db.select(Purok).order_by(Purok.name)
            ).all()
        ]


class DocumentStatusForm(BaseForm):
    """Form for updating document request status."""
    
    status = SelectField(
        'Status',
        validators=[DataRequired(message='Select a status')],
        choices=[
            ('UNDER_REVIEW', 'Under Review'),
            ('PROCESSING', 'Processing'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected')
        ],
        render_kw={'class': 'form-select'}
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[
            Optional(),
            Length(max=500, message='Notes cannot exceed 500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def validate_notes(self, field):
        """Require notes for rejection."""
        if self.status.data == 'REJECTED' and not field.data:
            raise ValidationError('A rejection reason is required')


class AdditionalRequirementForm(BaseForm):
    """Form for requesting additional document requirements."""
    
    requirement_name = StringField(
        'Requirement Name',
        validators=[
            DataRequired(message='Requirement name is required'),
            Length(min=5, max=200, message='Requirement name must be 5-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    notes = TextAreaField(
        'Instructions',
        validators=[
            Optional(),
            Length(max=500, message='Instructions cannot exceed 500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )


class BlotterStatusForm(BaseForm):
    """Form for updating blotter case status."""
    
    status = SelectField(
        'Status',
        validators=[DataRequired(message='Select a status')],
        choices=[
            ('UNDER_MEDIATION', 'Under Mediation'),
            ('HEARING_SCHEDULED', 'Hearing Scheduled'),
            ('SETTLED', 'Settled'),
            ('ENDORSED', 'Endorsed'),
            ('CLOSED', 'Closed')
        ],
        render_kw={'class': 'form-select'}
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[
            Optional(),
            Length(max=1000, message='Notes cannot exceed 1000 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 4}
    )


class BlotterPartyForm(BaseForm):
    """Form for adding parties to blotter cases."""
    
    name = StringField(
        'Name',
        validators=[
            DataRequired(message='Party name is required'),
            Length(min=2, max=200, message='Name must be 2-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    role = SelectField(
        'Role',
        validators=[DataRequired(message='Select party role')],
        choices=[
            ('COMPLAINANT', 'Complainant'),
            ('RESPONDENT', 'Respondent'),
            ('WITNESS', 'Witness'),
            ('MEDIATOR', 'Mediator'),
            ('LEGAL_COUNSEL', 'Legal Counsel')
        ],
        render_kw={'class': 'form-select'}
    )
    
    contact_information = StringField(
        'Contact Information',
        validators=[Optional(), Length(max=255)],
        render_kw={'class': 'form-control'}
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 2}
    )


class BlotterHearingForm(BaseForm):
    """Form for scheduling blotter hearings."""
    
    scheduled_at = DateTimeLocalField(
        'Hearing Date & Time',
        validators=[DataRequired(message='Hearing date and time is required')],
        render_kw={'class': 'form-control'}
    )
    
    location = StringField(
        'Location',
        validators=[
            Optional(),
            Length(max=255, message='Location cannot exceed 255 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    notes = TextAreaField(
        'Notes',
        validators=[Optional(), Length(max=1000)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def validate_scheduled_at(self, field):
        """Ensure hearing is scheduled in the future."""
        if field.data and field.data <= datetime.now():
            raise ValidationError('Hearing must be scheduled in the future')


class BusinessForm(BaseForm):
    """Form for business registration records."""
    
    business_name = StringField(
        'Business Name',
        validators=[
            DataRequired(message='Business name is required'),
            Length(min=2, max=200, message='Business name must be 2-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    owner_id = SelectField(
        'Business Owner',
        coerce=coerce_optional_int,
        validators=[DataRequired(message='Select business owner')],
        render_kw={'class': 'form-select'}
    )
    
    business_address = StringField(
        'Business Address',
        validators=[
            DataRequired(message='Business address is required'),
            Length(min=5, max=255, message='Address must be 5-255 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    business_type = SelectField(
        'Business Type',
        validators=[DataRequired(message='Select business type')],
        choices=[
            ('', 'Select business type'),
            ('Retail', 'Retail Store'),
            ('Restaurant', 'Restaurant/Food Service'),
            ('Service', 'Service Business'),
            ('Manufacturing', 'Manufacturing'),
            ('Agriculture', 'Agriculture'),
            ('Online', 'Online Business'),
            ('Other', 'Other')
        ],
        render_kw={'class': 'form-select'}
    )
    
    permit_number = StringField(
        'Permit Number',
        validators=[
            DataRequired(message='Permit number is required'),
            Length(min=3, max=50, message='Permit number must be 3-50 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    registration_date = DateField(
        'Registration Date',
        validators=[DataRequired(message='Registration date is required')],
        render_kw={'class': 'form-control'}
    )
    
    expiration_date = DateField(
        'Expiration Date',
        validators=[DataRequired(message='Expiration date is required')],
        render_kw={'class': 'form-control'}
    )
    
    status = SelectField(
        'Status',
        choices=[
            ('ACTIVE', 'Active'),
            ('EXPIRED', 'Expired'),
            ('SUSPENDED', 'Suspended'),
            ('REVOKED', 'Revoked')
        ],
        default='ACTIVE',
        render_kw={'class': 'form-select'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate owner choices
        self.owner_id.choices = [('', 'Select owner')] + [
            (r.id, f"{r.last_name}, {r.first_name}") 
            for r in db.session.scalars(
                db.select(Resident).order_by(Resident.last_name, Resident.first_name)
            ).all()
        ]
    
    def validate_expiration_date(self, field):
        """Ensure expiration is after registration."""
        if field.data and self.registration_date.data:
            if field.data <= self.registration_date.data:
                raise ValidationError('Expiration date must be after registration date')


class CollectionForm(BaseForm):
    """Form for recording fee collections."""
    
    resident_id = SelectField(
        'Resident',
        coerce=coerce_optional_int,
        validators=[DataRequired(message='Select resident')],
        render_kw={'class': 'form-select'}
    )
    
    service = StringField(
        'Service',
        validators=[
            DataRequired(message='Service description is required'),
            Length(min=3, max=200, message='Service must be 3-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    amount = FloatField(
        'Amount',
        validators=[
            DataRequired(message='Amount is required'),
            NumberRange(min=0.01, max=100000, message='Amount must be between ₱0.01 and ₱100,000'),
            validate_currency_amount
        ],
        render_kw={'class': 'form-control', 'step': '0.01', 'min': '0.01'}
    )
    
    payment_method = SelectField(
        'Payment Method',
        choices=[
            ('CASH', 'Cash'),
            ('CHECK', 'Check'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('GCASH', 'GCash'),
            ('OTHER', 'Other')
        ],
        default='CASH',
        render_kw={'class': 'form-select'}
    )
    
    transaction_date = DateField(
        'Transaction Date',
        validators=[
            DataRequired(message='Transaction date is required'),
            validate_date_range(allow_future=False)
        ],
        render_kw={'class': 'form-control'}
    )
    
    reference_number = StringField(
        'Reference Number',
        validators=[Optional(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate resident choices
        self.resident_id.choices = [('', 'Select resident')] + [
            (r.id, f"{r.last_name}, {r.first_name}") 
            for r in db.session.scalars(
                db.select(Resident).order_by(Resident.last_name, Resident.first_name)
            ).all()
        ]


class CorrectionReviewForm(BaseForm):
    """Form for reviewing resident correction requests."""
    
    action = HiddenField(validators=[DataRequired()])
    
    review_notes = TextAreaField(
        'Review Notes',
        validators=[
            Optional(),
            Length(max=1000, message='Notes cannot exceed 1000 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def validate_review_notes(self, field):
        """Require notes for rejection."""
        if self.action.data == 'reject' and not field.data:
            raise ValidationError('A rejection reason is required')


class QueueUpdateForm(BaseForm):
    """Form for updating queue request status."""
    
    status = SelectField(
        'Status',
        validators=[DataRequired(message='Select status')],
        choices=[
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('READY', 'Ready'),
            ('SCHEDULED', 'Scheduled'),
            ('COMPLETED', 'Completed'),
            ('CLOSED', 'Closed')
        ],
        render_kw={'class': 'form-select'}
    )
    
    assigned_official_id = SelectField(
        'Assigned Official',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    appointment_date = DateField(
        'Appointment Date',
        validators=[Optional()],
        render_kw={'class': 'form-control'}
    )
    
    appointment_time = TimeField(
        'Appointment Time',
        validators=[Optional()],
        render_kw={'class': 'form-control'}
    )
    
    remarks = TextAreaField(
        'Remarks',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate official choices
        self.assigned_official_id.choices = [('', 'No assignment')] + [
            (u.id, u.username) 
            for u in db.session.scalars(
                db.select(User).join(User.roles).where(
                    db.or_(
                        db.text("roles.name = 'Barangay Official'"),
                        db.text("roles.name = 'System Administrator'")
                    )
                ).order_by(User.username)
            ).all()
        ]


class WelfareForm(BaseForm):
    """Form for social welfare beneficiary registration."""
    
    resident_id = SelectField(
        'Resident',
        coerce=coerce_optional_int,
        validators=[DataRequired(message='Select resident')],
        render_kw={'class': 'form-select'}
    )
    
    category = SelectField(
        'Beneficiary Category',
        validators=[DataRequired(message='Select category')],
        choices=[
            ('', 'Select category'),
            ('SENIOR', 'Senior Citizens'),
            ('PWD', 'PWD'),
            ('4PS', '4Ps Beneficiaries'),
            ('SOLO_PARENT', 'Solo Parents'),
            ('PREGNANT', 'Pregnant Women'),
            ('NEWBORN', 'Newborns')
        ],
        render_kw={'class': 'form-select'}
    )
    
    application_status = SelectField(
        'Application Status',
        choices=[
            ('PENDING', 'Pending'),
            ('APPROVED', 'Approved'),
            ('REJECTED', 'Rejected'),
            ('ACTIVE', 'Active'),
            ('INACTIVE', 'Inactive')
        ],
        default='PENDING',
        render_kw={'class': 'form-select'}
    )
    
    registered_date = DateField(
        'Registration Date',
        validators=[DataRequired(message='Registration date is required')],
        render_kw={'class': 'form-control'}
    )
    
    application_notes = TextAreaField(
        'Application Notes',
        validators=[Optional(), Length(max=1000)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate resident choices
        self.resident_id.choices = [('', 'Select resident')] + [
            (r.id, f"{r.last_name}, {r.first_name}") 
            for r in db.session.scalars(
                db.select(Resident).order_by(Resident.last_name, Resident.first_name)
            ).all()
        ]


class AssistanceForm(BaseForm):
    """Form for recording assistance distribution."""
    
    beneficiary_id = HiddenField(validators=[DataRequired()])
    
    assistance_type = StringField(
        'Assistance Type',
        validators=[
            DataRequired(message='Assistance type is required'),
            Length(min=3, max=200, message='Type must be 3-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    quantity = IntegerField(
        'Quantity',
        validators=[
            DataRequired(message='Quantity is required'),
            NumberRange(min=1, max=10000, message='Quantity must be between 1 and 10,000')
        ],
        default=1,
        render_kw={'class': 'form-control'}
    )
    
    assistance_date = DateField(
        'Assistance Date',
        validators=[
            DataRequired(message='Assistance date is required'),
            validate_date_range(allow_future=False)
        ],
        render_kw={'class': 'form-control'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 2}
    )
    
    remarks = TextAreaField(
        'Remarks',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 2}
    )
