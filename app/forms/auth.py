"""Authentication form validation classes."""

from datetime import date, datetime
from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from app.registration import EDUCATION, RELATIONSHIPS, DURATIONS, CATEGORIES
from wtforms import (
    StringField, PasswordField, EmailField, DateField, SelectField,
    TextAreaField, BooleanField, HiddenField, SelectMultipleField
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError
)
from sqlalchemy import or_

from app.extensions import db
from app.models import User, Purok
from .common import (
    BaseForm, coerce_optional_int, validate_phone_number, validate_email_format, 
    validate_date_range, validate_person_name, sanitize_input
)


class LoginForm(BaseForm):
    """User login form with rate limiting awareness."""
    
    identifier = StringField(
        'Username or Email',
        validators=[
            DataRequired(message='Enter your username or email'),
            Length(min=3, max=255, message='Username/email must be 3-255 characters')
        ],
        render_kw={
            'placeholder': 'Username or email address',
            'autocomplete': 'username',
            'class': 'form-control'
        }
    )
    
    password = PasswordField(
        'Password',
        validators=[
            DataRequired(message='Enter your password'),
            Length(min=1, max=255, message='Password is required')
        ],
        render_kw={
            'placeholder': 'Password',
            'autocomplete': 'current-password',
            'class': 'form-control'
        }
    )
    
    remember_me = BooleanField(
        'Keep me signed in',
        default=False,
        render_kw={'class': 'form-check-input'}
    )
    
    def validate_identifier(self, field):
        """Sanitize and basic validation for identifier."""
        if field.data:
            field.data = sanitize_input(field.data.lower().strip())


class RegisterForm(BaseForm):
    """Comprehensive user registration form with resident details."""
    
    # Personal Information
    first_name = StringField(
        'First Name',
        validators=[
            DataRequired(message='First name is required'),
            Length(min=2, max=100, message='First name must be 2-100 characters'),
            validate_person_name,
        ],
        render_kw={
            'placeholder': 'First name',
            'class': 'form-control',
            'pattern': '[a-zA-Z\\s\\-\\.]+',
            'title': 'Only letters, spaces, hyphens, and periods allowed'
        }
    )
    
    middle_name = StringField(
        'Middle Name',
        validators=[
            Optional(),
            Length(max=100, message='Middle name cannot exceed 100 characters'),
            validate_person_name,
        ],
        render_kw={
            'placeholder': 'Middle name (optional)',
            'class': 'form-control',
            'pattern': '[a-zA-Z\\s\\-\\.]*'
        }
    )
    
    last_name = StringField(
        'Last Name',
        validators=[
            DataRequired(message='Last name is required'),
            Length(min=2, max=100, message='Last name must be 2-100 characters'),
            validate_person_name,
        ],
        render_kw={
            'placeholder': 'Last name',
            'class': 'form-control',
            'pattern': '[a-zA-Z\\s\\-\\.]+',
            'title': 'Only letters, spaces, hyphens, and periods allowed'
        }
    )
    
    suffix = StringField(
        'Suffix',
        validators=[
            Optional(),
            Length(max=20, message='Suffix cannot exceed 20 characters')
        ],
        render_kw={
            'placeholder': 'Jr., Sr., III, etc. (optional)',
            'class': 'form-control'
        }
    )
    
    birth_date = DateField(
        'Birth Date',
        validators=[
            DataRequired(message='Birth date is required'),
            validate_date_range(
                min_date=date(1900, 1, 1),
                max_date=date.today(),
                allow_future=False
            )
        ],
        render_kw={
            'class': 'form-control',
            'max': date.today().isoformat()
        }
    )
    
    sex = SelectField(
        'Sex',
        choices=[
            ('', 'Select sex'),
            ('Male', 'Male'),
            ('Female', 'Female'),
            ('Other', 'Other'),
        ],
        validators=[Optional()],
        render_kw={'class': 'form-select'}
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

    nationality = StringField(
        'Nationality',
        validators=[
            DataRequired(message='Nationality is required'),
            Length(min=2, max=80, message='Nationality must be 2-80 characters')
        ],
        default='Filipino',
        render_kw={'placeholder': 'e.g., Filipino', 'class': 'form-control'}
    )
    
    place_of_birth = StringField('Place of birth (municipality/city, province)', validators=[Optional(), Length(max=200)])
    religion = SelectField('Religion (optional)', choices=[('', 'Select religion'), ('Roman Catholic', 'Roman Catholic'), ('Christian', 'Christian'), ('Islam', 'Islam'), ('Iglesia Ni Cristo', 'Iglesia Ni Cristo'), ('Buddhism', 'Buddhism'), ('Hinduism', 'Hinduism'), ('Other', 'Other'), ('None', 'None'), ('Prefer not to say', 'Prefer not to say')], validators=[Optional()])
    educational_attainment = SelectField('Educational attainment', choices=EDUCATION, validators=[Optional()])
    household_relationship = SelectField('Relationship to household head', choices=RELATIONSHIPS, validators=[Optional()])
    house_no = StringField('House no. / lot / block', validators=[Optional(), Length(max=100)])
    street_landmark = StringField('Street / sitio / nearest landmark', validators=[Optional(), Length(max=155)])
    residency_duration = SelectField('Duration of continuous residency', choices=DURATIONS, validators=[Optional()])
    special_categories = SelectMultipleField('Special status / welfare classifications', choices=CATEGORIES, validators=[Optional()])
    emergency_contact_name = StringField('Emergency contact name', validators=[Optional(), Length(max=200)])
    emergency_contact_relationship = StringField('Emergency contact relationship', validators=[Optional(), Length(max=80)])
    emergency_contact_number = StringField('Emergency contact number', validators=[Optional(), validate_phone_number, Length(max=30)])
    profile_photo = FileField('Resident identification photo (optional)', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Only JPEG, PNG or WebP profile photos are allowed.')])
    proof_of_residency = FileField('Proof of residency', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Only JPEG and PNG images are allowed.')])
    philsys_card = FileField('PhilSys identification image (optional)', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Only JPEG and PNG images are allowed.')])

    def validate_emergency_contact_name(self, field):
        if self.emergency_contact_number.data and not field.data:
            raise ValidationError('Enter the emergency contact name.')

    def validate_emergency_contact_number(self, field):
        if self.emergency_contact_name.data and not field.data:
            raise ValidationError('Enter the emergency contact number.')

    def validate_special_categories(self, field):
        if 'senior' in (field.data or []) and self.birth_date.data:
            today = date.today()
            age = today.year - self.birth_date.data.year - ((today.month, today.day) < (self.birth_date.data.month, self.birth_date.data.day))
            if age < 60:
                raise ValidationError('Senior Citizen classification requires an age of at least 60.')

    # Contact Information
    contact_number = StringField(
        'Contact Number',
        validators=[
            Optional(),
            validate_phone_number
        ],
        render_kw={
            'placeholder': '09171234567 or (049) 559-0123',
            'class': 'form-control',
            'pattern': '[0-9\\(\\)\\+\\-\\s]+',
            'title': 'Enter a valid Philippine phone number'
        }
    )
    
    email = EmailField(
        'Email Address',
        validators=[
            DataRequired(message='Email address is required'),
            Email(message='Enter a valid email address'),
            Length(max=255, message='Email cannot exceed 255 characters'),
            validate_email_format
        ],
        render_kw={
            'placeholder': 'your.email@example.com',
            'class': 'form-control',
            'autocomplete': 'email'
        }
    )
    
    address_line = StringField(
        'Address',
        validators=[
            Optional(),
            Length(max=255, message='Address cannot exceed 255 characters')
        ],
        render_kw={
            'placeholder': 'Complete address (optional)',
            'class': 'form-control'
        }
    )
    
    occupation = StringField(
        'Occupation',
        validators=[
            Optional(),
            Length(max=150, message='Occupation cannot exceed 150 characters')
        ],
        render_kw={
            'placeholder': 'Occupation (optional)',
            'class': 'form-control'
        }
    )

    voter_status = SelectField(
        'Voter Status',
        choices=[
            ('unknown', 'Not specified'),
            ('registered', 'Registered voter'),
            ('not_registered', 'Not registered'),
            ('pending', 'For registration')
        ],
        default='unknown',
        validators=[DataRequired()],
        render_kw={'class': 'form-select'}
    )
    
    purok_id = SelectField(
        'Purok',
        coerce=coerce_optional_int,
        validators=[Optional()],
        render_kw={'class': 'form-select'}
    )
    
    privacy_consent = BooleanField(
        'Privacy Consent',
        validators=[
            DataRequired(message='You must accept the privacy notice to register')
        ],
        render_kw={'class': 'form-check-input'}
    )
    
    terms_consent = BooleanField(
        'Terms and Conditions',
        validators=[
            DataRequired(message='You must accept the terms and conditions to register')
        ],
        render_kw={'class': 'form-check-input'}
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if current_app.config.get("REGISTRATION_REQUIRE_COMPLETE_PROFILE", True):
            for name in ("place_of_birth", "house_no", "street_landmark", "residency_duration", "purok_id"):
                field = getattr(self, name)
                field.validators = [DataRequired()] + [v for v in field.validators if not isinstance(v, Optional)]
                field.flags.required = True
            self.proof_of_residency.validators = [FileRequired(), FileAllowed(["jpg", "jpeg", "png"])]
            self.proof_of_residency.flags.required = True
        # Populate purok choices
        self.emergency_contact_name.render_kw['data-required-with'] = 'emergency_contact_number'
        self.emergency_contact_number.render_kw['data-required-with'] = 'emergency_contact_name'
        today = date.today()
        try:
            youngest = today.replace(year=today.year-10)
        except ValueError:
            youngest = today.replace(year=today.year-10, day=28)
        self.birth_date.render_kw['max'] = youngest.isoformat()
        self.special_categories.render_kw.update({'data-min-age':'60','data-age-value':'senior'})
        self.purok_id.choices = [('', 'Select purok')] + [
            (p.id, p.name) for p in db.session.scalars(
                db.select(Purok).where(Purok.status == 'active').order_by(Purok.name)
            ).all()
        ]
    
    def validate_birth_date(self, field):
        """Match the registration page's minimum age of 10 years and block dates before 1900."""
        if field.data:
            # Check minimum age (10 years old)
            today = date.today()
            try:
                youngest_allowed = today.replace(year=today.year - 10)
            except ValueError:
                youngest_allowed = today.replace(year=today.year - 10, day=28)
            if field.data > youngest_allowed:
                raise ValidationError('You must be at least 10 years old to register')
            
            # Block dates before 1900
            if field.data < date(1900, 1, 1):
                raise ValidationError('Birth date must be after January 1, 1900')
    
    def validate_email(self, field):
        """Check email is unique."""
        if field.data:
            email = sanitize_input(field.data.lower().strip())
            
            if db.session.scalar(db.select(User).where(User.email == email)):
                raise ValidationError('That email address is already registered')
            
            field.data = email
    
class ChangePasswordForm(BaseForm):
    """Form for changing password of authenticated user."""
    
    current_password = PasswordField(
        'Current Password',
        validators=[
            DataRequired(message='Current password is required')
        ],
        render_kw={
            'placeholder': 'Enter your current password',
            'class': 'form-control',
            'autocomplete': 'current-password'
        }
    )
    
    new_password = PasswordField(
        'New Password',
        validators=[
            DataRequired(message='New password is required'),
            Length(min=8, message='Password must be at least 8 characters')
        ],
        render_kw={
            'placeholder': 'Enter new password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }
    )
    
    password_confirmation = PasswordField(
        'Confirm New Password',
        validators=[
            DataRequired(message='Password confirmation is required'),
            EqualTo('new_password', message='Passwords must match')
        ],
        render_kw={
            'placeholder': 'Confirm new password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }
    )
    
    def validate_new_password(self, field):
        """Enhanced password validation."""
        if field.data:
            password = field.data
            
            # Check minimum length from config
            min_length = current_app.config.get('PASSWORD_MIN_LENGTH', 8)
            if len(password) < min_length:
                raise ValidationError(f'Password must be at least {min_length} characters')
            
            # Check complexity
            has_lower = any(c.islower() for c in password)
            has_upper = any(c.isupper() for c in password)
            has_digit = any(c.isdigit() for c in password)
            
            if not (has_lower and has_upper and has_digit):
                raise ValidationError('Password must contain uppercase, lowercase, and numbers')


class ForgotPasswordForm(BaseForm):
    """Form for requesting password reset."""
    
    email = EmailField(
        'Email Address',
        validators=[
            DataRequired(message='Email address is required'),
            Email(message='Enter a valid email address'),
            validate_email_format
        ],
        render_kw={
            'placeholder': 'Enter your registered email address',
            'class': 'form-control',
            'autocomplete': 'email'
        }
    )


class ResetPasswordForm(BaseForm):
    """Form for resetting password with token."""
    
    password = PasswordField(
        'New Password',
        validators=[
            DataRequired(message='Password is required'),
            Length(min=8, message='Password must be at least 8 characters')
        ],
        render_kw={
            'placeholder': 'Enter new password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }
    )
    
    password_confirmation = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(message='Password confirmation is required'),
            EqualTo('password', message='Passwords must match')
        ],
        render_kw={
            'placeholder': 'Confirm new password',
            'class': 'form-control',
            'autocomplete': 'new-password'
        }
    )
    
    def validate_password(self, field):
        """Enhanced password validation."""
        if field.data:
            password = field.data
            
            # Check minimum length from config
            min_length = current_app.config.get('PASSWORD_MIN_LENGTH', 8)
            if len(password) < min_length:
                raise ValidationError(f'Password must be at least {min_length} characters')
            
            # Check complexity
            has_lower = any(c.islower() for c in password)
            has_upper = any(c.isupper() for c in password)
            has_digit = any(c.isdigit() for c in password)
            
            if not (has_lower and has_upper and has_digit):
                raise ValidationError('Password must contain uppercase, lowercase, and numbers')
