"""Admin portal form validation classes."""

from flask import current_app
from sqlalchemy import func
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField, SelectField, IntegerField, FloatField,
    BooleanField, HiddenField, PasswordField, DateField
)
from wtforms.validators import (
    DataRequired, Length, Optional, NumberRange, ValidationError, EqualTo, Regexp
)

from app.extensions import db
from app.models import User, Role, DocumentType, Purok
from .common import (
    BaseForm, coerce_optional_int, validate_email_format, validate_phone_number, 
    validate_currency_amount, sanitize_input
)


class UserForm(BaseForm):
    """Form for creating/editing user accounts."""
    
    username = StringField(
        'Username',
        validators=[
            DataRequired(message='Username is required'),
            Length(min=3, max=80, message='Username must be 3-80 characters'),
            Regexp(
                r'^[A-Za-z0-9._-]+$',
                message='Username can only contain letters, numbers, dots, underscores, and hyphens'
            )
        ],
        render_kw={'class': 'form-control'}
    )
    
    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email is required'),
            validate_email_format,
            Length(max=120)
        ],
        render_kw={'class': 'form-control'}
    )
    
    password = PasswordField(
        'Password',
        validators=[
            Optional(),  # Optional for edit mode
            Length(min=8, message='Password must be at least 8 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[
            EqualTo('password', message='Passwords must match')
        ],
        render_kw={'class': 'form-control'}
    )
    
    role_id = SelectField(
        'Role',
        coerce=coerce_optional_int,
        validators=[DataRequired(message='Select a role')],
        render_kw={'class': 'form-select'}
    )
    
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )

    attendance_personnel_id = SelectField(
        'Attendance personnel record', coerce=coerce_optional_int,
        validators=[Optional()], default=None,
    )
    
    profile_first_name = StringField(
        'First Name',
        validators=[Optional(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    
    profile_last_name = StringField(
        'Last Name',
        validators=[Optional(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    
    profile_phone = StringField(
        'Phone Number',
        validators=[Optional(), validate_phone_number],
        render_kw={'class': 'form-control'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate role choices
        self.role_id.choices = [
            (r.id, r.name) for r in db.session.scalars(
                db.select(Role).order_by(Role.name)
            ).all() if r.name.casefold() != "barangay official"
        ]
        from app.attendance.accounts import personnel_choices
        self.attendance_personnel_id.choices = personnel_choices()
    
    def validate_password(self, field):
        if not hasattr(self, "edit_user_id") and not field.data:
            raise ValidationError("Password is required")
        if field.data and len(field.data) < current_app.config.get("PASSWORD_MIN_LENGTH", 12):
            raise ValidationError("Password does not meet the configured minimum length")

    def validate_username(self, field):
        """Check username uniqueness."""
        if hasattr(self, 'edit_user_id'):
            # Edit mode - exclude current user from check
            existing = db.session.scalar(
                db.select(User).where(
                    User.username == field.data,
                    User.id != self.edit_user_id
                )
            )
        else:
            # Create mode
            existing = db.session.scalar(
                db.select(User).where(User.username == field.data)
            )
        
        if existing:
            raise ValidationError('Username already exists')
    
    def validate_email(self, field):
        """Check email uniqueness."""
        if hasattr(self, 'edit_user_id'):
            # Edit mode - exclude current user from check
            existing = db.session.scalar(
                db.select(User).where(
                    User.email == field.data,
                    User.id != self.edit_user_id
                )
            )
        else:
            # Create mode
            existing = db.session.scalar(
                db.select(User).where(User.email == field.data)
            )
        
        if existing:
            raise ValidationError('Email already exists')


class RoleForm(BaseForm):
    """Form for creating/editing user roles."""
    
    name = StringField(
        'Role Name',
        validators=[
            DataRequired(message='Role name is required'),
            Length(min=3, max=80, message='Role name must be 3-80 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=255)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    def validate_name(self, field):
        """Check role name uniqueness."""
        if hasattr(self, 'edit_role_id'):
            # Edit mode - exclude current role from check
            existing = db.session.scalar(
                db.select(Role).where(
                    Role.name == field.data,
                    Role.id != self.edit_role_id
                )
            )
        else:
            # Create mode
            existing = db.session.scalar(
                db.select(Role).where(Role.name == field.data)
            )
        
        if existing:
            raise ValidationError('Role name already exists')


class DocumentTypeForm(BaseForm):
    """Form for creating/editing document types."""
    
    name = StringField(
        'Document Name',
        validators=[
            DataRequired(message='Document name is required'),
            Length(min=3, max=200, message='Document name must be 3-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    fee = FloatField(
        'Fee (₱)',
        validators=[
            DataRequired(message='Fee is required'),
            NumberRange(min=0, max=10000, message='Fee must be between ₱0 and ₱10,000'),
            validate_currency_amount
        ],
        render_kw={'class': 'form-control', 'step': '0.01', 'min': '0'}
    )
    
    processing_days = IntegerField(
        'Processing Days',
        validators=[
            DataRequired(message='Processing days required'),
            NumberRange(min=0, max=30, message='Processing days must be 0-30')
        ],
        render_kw={'class': 'form-control'}
    )
    
    requirements = TextAreaField(
        'Requirements',
        validators=[Optional(), Length(max=1000)],
        render_kw={'class': 'form-control', 'rows': 4}
    )
    
    template_content = TextAreaField(
        'Template Content',
        validators=[Optional(), Length(max=5000)],
        render_kw={'class': 'form-control', 'rows': 8}
    )
    
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )
    
    def validate_name(self, field):
        """Check document type name uniqueness."""
        if hasattr(self, 'edit_doc_type_id'):
            # Edit mode - exclude current document type from check
            existing = db.session.scalar(
                db.select(DocumentType).where(
                    DocumentType.name == field.data,
                    DocumentType.id != self.edit_doc_type_id
                )
            )
        else:
            # Create mode
            existing = db.session.scalar(
                db.select(DocumentType).where(DocumentType.name == field.data)
            )
        
        if existing:
            raise ValidationError('Document type name already exists')


class PurokForm(BaseForm):
    """Form for creating/editing purok records."""
    
    name = StringField(
        'Purok Name',
        validators=[
            DataRequired(message='Purok name is required'),
            Length(min=2, max=100, message='Purok name must be 2-100 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=255)],
        render_kw={'class': 'form-control', 'rows': 2}
    )
    
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )
    
    def validate_name(self, field):
        from app.normalization import purok_identity
        try:
            field.data, key, number = purok_identity(field.data)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        query = db.select(Purok).where(Purok.name_key == key)
        if number is not None:
            from sqlalchemy import or_
            query = db.select(Purok).where(or_(Purok.name_key == key, Purok.purok_number == number))
        if hasattr(self, 'edit_purok_id'):
            query = query.where(Purok.id != self.edit_purok_id)
        if db.session.scalar(query):
            raise ValidationError('This Purok already exists, including archived records.')


class SystemSettingsForm(BaseForm):
    """Form for system settings configuration."""
    
    barangay_name = StringField(
        'Barangay Name',
        validators=[
            DataRequired(message='Barangay name is required'),
            Length(min=3, max=150, message='Barangay name must be 3-150 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    barangay_address = TextAreaField(
        'Barangay Address',
        validators=[
            DataRequired(message='Barangay address is required'),
            Length(min=10, max=500, message='Address must be 10-500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    contact_number = StringField(
        'Contact Number',
        validators=[
            DataRequired(message='Contact number is required'),
            validate_phone_number
        ],
        render_kw={'class': 'form-control'}
    )
    
    email_address = StringField(
        'Email Address',
        validators=[
            DataRequired(message='Email address is required'),
            validate_email_format,
            Length(max=255)
        ],
        render_kw={'class': 'form-control'}
    )
    
    captain_name = StringField(
        'Barangay Captain',
        validators=[
            DataRequired(message='Captain name is required'),
            Length(min=3, max=150, message='Captain name must be 3-150 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    secretary_name = StringField(
        'Barangay Secretary',
        validators=[
            Optional(),
            Length(max=150, message='Secretary name cannot exceed 150 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    treasurer_name = StringField(
        'Barangay Treasurer',
        validators=[
            Optional(),
            Length(max=150, message='Treasurer name cannot exceed 150 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    office_hours = TextAreaField(
        'Office Hours',
        validators=[
            Optional(),
            Length(max=500, message='Office hours cannot exceed 500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )


class FeeScheduleForm(BaseForm):
    """Form for managing fee schedules."""
    
    service_name = StringField(
        'Service Name',
        validators=[
            DataRequired(message='Service name is required'),
            Length(min=3, max=200, message='Service name must be 3-200 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    base_fee = FloatField(
        'Base Fee (₱)',
        validators=[
            DataRequired(message='Base fee is required'),
            NumberRange(min=0, max=50000, message='Fee must be between ₱0 and ₱50,000'),
            validate_currency_amount
        ],
        render_kw={'class': 'form-control', 'step': '0.01', 'min': '0'}
    )
    
    additional_fee = FloatField(
        'Additional Fee (₱)',
        validators=[
            Optional(),
            NumberRange(min=0, max=10000, message='Additional fee must be between ₱0 and ₱10,000'),
            validate_currency_amount
        ],
        default=0.00,
        render_kw={'class': 'form-control', 'step': '0.01', 'min': '0'}
    )
    
    fee_type = SelectField(
        'Fee Type',
        validators=[DataRequired(message='Select fee type')],
        choices=[
            ('FIXED', 'Fixed Fee'),
            ('VARIABLE', 'Variable Fee'),
            ('PERCENTAGE', 'Percentage-based'),
            ('TIERED', 'Tiered Pricing')
        ],
        render_kw={'class': 'form-select'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=500)],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    is_active = BooleanField(
        'Active',
        default=True,
        render_kw={'class': 'form-check-input'}
    )


class BackupRestoreForm(BaseForm):
    """Form for database backup and restore operations."""
    
    backup_name = StringField(
        'Backup Name',
        validators=[
            DataRequired(message='Backup name is required'),
            Length(min=3, max=100, message='Backup name must be 3-100 characters')
        ],
        render_kw={'class': 'form-control'}
    )
    
    description = TextAreaField(
        'Description',
        validators=[Optional(), Length(max=255)],
        render_kw={'class': 'form-control', 'rows': 2}
    )
    
    include_files = BooleanField(
        'Include uploaded files',
        default=True,
        render_kw={'class': 'form-check-input'}
    )


class AuditLogFilterForm(FlaskForm):
    """Form for filtering audit logs."""
    
    user_id = SelectField(
        'User',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    action = SelectField(
        'Action',
        validators=[Optional()],
        choices=[
            ('', 'All actions'),
            ('CREATE', 'Create'),
            ('READ', 'Read'),
            ('UPDATE', 'Update'),
            ('DELETE', 'Delete'),
            ('LOGIN', 'Login'),
            ('LOGOUT', 'Logout')
        ],
        render_kw={'class': 'form-select'}
    )
    
    table_name = StringField(
        'Table/Resource',
        validators=[Optional(), Length(max=100)],
        render_kw={'class': 'form-control'}
    )
    
    date_from = StringField(
        'Date From',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    date_to = StringField(
        'Date To',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate user choices
        self.user_id.choices = [('', 'All users')] + [
            (u.id, u.username) for u in db.session.scalars(
                db.select(User).order_by(User.username)
            ).all()
        ]


class ReportGenerationForm(BaseForm):
    """Form for generating system reports."""
    
    report_type = SelectField(
        'Report Type',
        validators=[DataRequired(message='Select report type')],
        choices=[
            ('', 'Select report type'),
            ('RESIDENTS', 'Residents Report'),
            ('DOCUMENTS', 'Document Requests Report'),
            ('BLOTTER', 'Blotter Cases Report'),
            ('BUSINESS', 'Business Permits Report'),
            ('COLLECTIONS', 'Fee Collections Report'),
            ('WELFARE', 'Social Welfare Report'),
            ('AUDIT', 'System Audit Report')
        ],
        render_kw={'class': 'form-select'}
    )
    
    date_from = StringField(
        'Date From',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    date_to = StringField(
        'Date To',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'type': 'date'}
    )
    
    format = SelectField(
        'Export Format',
        validators=[DataRequired(message='Select export format')],
        choices=[
            ('PDF', 'PDF'),
            ('EXCEL', 'Excel'),
            ('CSV', 'CSV')
        ],
        default='PDF',
        render_kw={'class': 'form-select'}
    )
    
    include_archived = BooleanField(
        'Include archived records',
        default=False,
        render_kw={'class': 'form-check-input'}
    )


class BulkOperationForm(BaseForm):
    """Form for bulk operations on records."""
    
    operation = SelectField(
        'Operation',
        validators=[DataRequired(message='Select operation')],
        choices=[
            ('', 'Select operation'),
            ('ACTIVATE', 'Activate Selected'),
            ('DEACTIVATE', 'Deactivate Selected'),
            ('DELETE', 'Delete Selected'),
            ('EXPORT', 'Export Selected'),
            ('ARCHIVE', 'Archive Selected')
        ],
        render_kw={'class': 'form-select'}
    )
    
    selected_ids = HiddenField(
        validators=[DataRequired(message='No records selected')]
    )
    
    confirmation = BooleanField(
        'I confirm this operation',
        validators=[DataRequired(message='Please confirm the operation')],
        render_kw={'class': 'form-check-input'}
    )
    
    reason = TextAreaField(
        'Reason (for audit trail)',
        validators=[
            Optional(),
            Length(max=500, message='Reason cannot exceed 500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 2}
    )


class MaintenanceModeForm(BaseForm):
    """Form for system maintenance mode configuration."""
    
    enable_maintenance = BooleanField(
        'Enable Maintenance Mode',
        render_kw={'class': 'form-check-input'}
    )
    
    maintenance_message = TextAreaField(
        'Maintenance Message',
        validators=[
            Optional(),
            Length(max=500, message='Message cannot exceed 500 characters')
        ],
        render_kw={'class': 'form-control', 'rows': 3}
    )
    
    allowed_ips = TextAreaField(
        'Allowed IP Addresses (one per line)',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'rows': 4}
    )


class OfficialAccountForm(BaseForm):
    """Create an official login and its official-profile record together."""

    email = StringField(
        'Email', validators=[DataRequired(), validate_email_format, Length(max=255)],
        render_kw={'class': 'civic-input', 'type': 'email', 'autocomplete': 'email'}
    )
    full_name = StringField(
        'Full name', validators=[DataRequired(), Length(min=2, max=200)],
        render_kw={'class': 'civic-input', 'autocomplete': 'name'}
    )
    position = StringField(
        'Position', validators=[DataRequired(), Length(min=2, max=100)],
        render_kw={'class': 'civic-input'}
    )
    birth_date = DateField(
        'Birthdate', format='%Y-%m-%d', validators=[DataRequired()],
        render_kw={'class': 'civic-input', 'type': 'date'}
    )
    term_start = DateField(
        'Term start', format='%Y-%m-%d', validators=[DataRequired()],
        render_kw={'class': 'civic-input', 'type': 'date'}
    )
    term_end = DateField(
        'Term end', format='%Y-%m-%d', validators=[Optional()],
        render_kw={'class': 'civic-input', 'type': 'date'}
    )
    contact_number = StringField(
        'Contact number', validators=[Optional(), validate_phone_number, Length(max=30)],
        render_kw={'class': 'civic-input', 'type': 'tel', 'autocomplete': 'tel'}
    )
    attendance_personnel_id = SelectField(
        'Attendance personnel record', coerce=coerce_optional_int,
        validators=[Optional()], default=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.attendance.accounts import personnel_choices
        self.attendance_personnel_id.choices = personnel_choices()

    def validate_email(self, field):
        field.data = field.data.strip().lower()
        if db.session.scalar(db.select(User).where(func.lower(User.email) == field.data)):
            raise ValidationError('Email already exists.')

    def validate_term_end(self, field):
        if field.data and self.term_start.data and field.data < self.term_start.data:
            raise ValidationError('Term end cannot be before term start.')
