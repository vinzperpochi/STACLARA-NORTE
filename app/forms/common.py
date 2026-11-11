"""Common validation utilities and custom validators."""

import re
from datetime import date, datetime
from typing import Any
import bleach
from flask import current_app
from flask_wtf import FlaskForm
from wtforms import ValidationError as WTFormsValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp
from werkzeug.datastructures import FileStorage

CLIENT_INPUT_TYPES = {'IntegerField':'number','FloatField':'number','DecimalField':'number',
                      'DateField':'date','DateTimeLocalField':'datetime-local','TimeField':'time'}


def coerce_optional_int(value):
    """Coerce numeric select choices while treating the blank option as None."""
    if value in (None, ""):
        return None
    return int(value)


def validate_person_name(form, field):
    """Reject markup, digits, and unsupported punctuation in person names."""
    value = (field.data or "").strip()
    if value and (
        not any(character.isalpha() for character in value)
        or any(not (character.isalpha() or character in " -.") for character in value)
    ):
        raise WTFormsValidationError("Use letters, spaces, hyphens, and periods only")
    field.data = value


class ValidationError(Exception):
    """Custom validation error with user-friendly messages."""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)


def validate_phone_number(form, field):
    """Validate Philippine phone number formats."""
    if not field.data:
        return
    
    phone = re.sub(r'\D', '', field.data)  # Remove non-digits
    
    # Philippine mobile: 09xxxxxxxxx or +639xxxxxxxxx
    # Landline: area code + 7 digits
    if not (
        (phone.startswith('09') and len(phone) == 11) or
        (phone.startswith('639') and len(phone) == 12) or
        (len(phone) >= 7 and len(phone) <= 11)  # Landline flexibility
    ):
        raise WTFormsValidationError(
            'Enter a valid Philippine phone number (e.g., 09171234567 or (049) 559-0123)'
        )


def validate_email_format(form, field):
    """Enhanced email validation with domain checks."""
    if not field.data:
        return
    
    email = field.data.lower().strip()
    
    # Basic email format check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise WTFormsValidationError('Enter a valid email address')
    
    # Check for common suspicious patterns
    suspicious_patterns = [
        r'^\d+@',  # Starts with numbers only
        r'@\d+\.',  # Domain starts with numbers
        r'\.\d+$'   # TLD is only numbers
    ]
    
    if any(re.search(pattern, email) for pattern in suspicious_patterns):
        raise WTFormsValidationError('Please use a standard email address format')


def validate_date_range(min_date=None, max_date=None, allow_future=True):
    """Validate date falls within specified range."""
    def _validate(form, field):
        if not field.data:
            return
        
        today = date.today()
        
        if isinstance(field.data, str):
            try:
                field_date = datetime.strptime(field.data, '%Y-%m-%d').date()
            except ValueError:
                raise WTFormsValidationError('Enter a valid date (YYYY-MM-DD)')
        else:
            field_date = field.data
        
        if min_date and field_date < min_date:
            raise WTFormsValidationError(f'Date cannot be before {min_date}')
        
        if max_date and field_date > max_date:
            raise WTFormsValidationError(f'Date cannot be after {max_date}')
        
        if not allow_future and field_date > today:
            raise WTFormsValidationError('Date cannot be in the future')
    
    _validate.client_constraints = {
        'min': min_date.isoformat() if min_date else None,
        'max': max_date.isoformat() if max_date else None,
        'data-no-future': 'true' if not allow_future else None,
    }
    return _validate


def validate_file_upload(allowed_extensions=None, max_size_mb=5):
    """Validate file uploads for safety and constraints."""
    def _validate(form, field):
        if not field.data or not isinstance(field.data, FileStorage):
            return
        
        file = field.data
        
        # Check if file was actually uploaded
        if not file.filename:
            raise WTFormsValidationError('Please select a file to upload')
        
        # Validate file extension
        if allowed_extensions:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext not in [e.lower() for e in allowed_extensions]:
                allowed_str = ', '.join(allowed_extensions)
                raise WTFormsValidationError(f'Only these file types are allowed: {allowed_str}')
        
        # Check file size (approximate, since we can't seek easily)
        if hasattr(file, 'content_length') and file.content_length:
            if file.content_length > max_size_mb * 1024 * 1024:
                raise WTFormsValidationError(f'File size must be under {max_size_mb}MB')
        
        # Validate filename for security
        if not re.match(r'^[a-zA-Z0-9._-]+$', file.filename):
            raise WTFormsValidationError('Filename contains invalid characters')
    
    _validate.client_constraints = {
        'data-allowed-extensions': ','.join(allowed_extensions) if allowed_extensions else None,
        'data-max-file-bytes': max_size_mb * 1024 * 1024,
    }
    return _validate


def sanitize_input(text: str, allow_html: bool = False) -> str:
    """Sanitize user input to prevent XSS and clean up text."""
    if not text:
        return ''
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    if not allow_html:
        # Remove all HTML tags
        text = bleach.clean(text, tags=[], strip=True)
    else:
        # Allow only safe HTML tags
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li']
        text = bleach.clean(text, tags=allowed_tags, strip=True)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text


def validate_purok_name(form, field):
    """Validate purok name format."""
    if not field.data:
        return
    
    name = field.data.strip()
    
    if len(name) < 2:
        raise WTFormsValidationError('Purok name must be at least 2 characters')
    
    if len(name) > 100:
        raise WTFormsValidationError('Purok name cannot exceed 100 characters')
    
    if not re.match(r'^[a-zA-Z0-9\s\-\.]+$', name):
        raise WTFormsValidationError('Purok name can only contain letters, numbers, spaces, hyphens, and periods')


def validate_currency_amount(form, field):
    """Validate currency amounts are positive and reasonable."""
    if field.data is None:
        return
    
    if field.data < 0:
        raise WTFormsValidationError('Amount cannot be negative')
    
    if field.data > 1000000:  # 1 million pesos max
        raise WTFormsValidationError('Amount seems unreasonably large')


class BaseForm(FlaskForm):
    """Base form class with common functionality."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_validation()
    
    def _setup_validation(self):
        """Expose existing field rules to the browser without changing server checks."""
        for name, field in self._fields.items():
            attrs = dict(field.render_kw or {})
            for validator in field.validators:
                attrs.update({key:value for key,value in getattr(validator,'client_constraints',{}).items()
                              if value is not None})
                if isinstance(validator, Length):
                    if validator.min > 0: attrs['minlength'] = validator.min
                    if validator.max is not None and validator.max >= 0: attrs['maxlength'] = validator.max
                if isinstance(validator, NumberRange):
                    if validator.min is not None: attrs['min'] = validator.min
                    if validator.max is not None: attrs['max'] = validator.max
                if isinstance(validator, EqualTo): attrs['data-equal-to'] = validator.fieldname
                if isinstance(validator, Regexp):
                    attrs['data-validation-pattern'] = validator.regex.pattern
                    if validator.message: attrs['data-pattern-message'] = validator.message
                if validator is validate_phone_number:
                    attrs.update(type='tel', **{'data-validate-phone':'true'})
                if validator is validate_email_format or isinstance(validator, Email): attrs['type'] = 'email'
                if validator is validate_email_format: attrs['data-standard-email'] = 'true'
                if validator is validate_person_name:
                    attrs.pop('pattern',None)  # Browser ASCII patterns rejected valid names such as Peña.
                    attrs['data-validate-name'] = 'true'
                # FileAllowed exposes its extension list, independent of upload widget type.
                if validator.__class__.__name__ == 'FileAllowed' and isinstance(validator.upload_set,(list,tuple,set)):
                    attrs['data-allowed-extensions'] = ','.join(validator.upload_set)
            if field.type in ('FloatField','DecimalField'): attrs.setdefault('step','any')
            if field.type in CLIENT_INPUT_TYPES: attrs.setdefault('type',CLIENT_INPUT_TYPES[field.type])
            if name == 'new_password' and self.__class__.__name__ in ('ChangePasswordForm','ResetPasswordForm'):
                attrs['minlength'] = max(attrs.get('minlength',0),current_app.config.get('PASSWORD_MIN_LENGTH',8))
                attrs['data-password-policy'] = 'complex'
            if name == 'password' and self.__class__.__name__ == 'UserForm':
                attrs['minlength'] = max(attrs.get('minlength',0),current_app.config.get('PASSWORD_MIN_LENGTH',12))
            if attrs.get('data-no-future'):
                today = date.today().isoformat()
                attrs['max'] = min(str(attrs.get('max') or today), today)
            if field.type == 'FileField' and 'data-max-file-bytes' not in attrs:
                extensions = set(attrs.get('data-allowed-extensions','').split(','))
                if extensions and extensions <= {'jpg','jpeg','png','webp'}:
                    attrs['data-max-file-bytes'] = current_app.config.get('MAX_IMAGE_BYTES',5*1024*1024)
            for end, start in [('end_date','start_date'),('effective_until','effective_from'),
                               ('term_end','term_start'),('expiration_date','registration_date')]:
                if name == end and start in self._fields: attrs['data-not-before'] = start
            field.render_kw = attrs
    
    def validate_and_sanitize(self):
        """Validate form and sanitize all text inputs."""
        if not self.validate():
            return False
        
        # Sanitize all text fields
        for field_name, field in self._fields.items():
            if hasattr(field, 'data') and isinstance(field.data, str):
                field.data = sanitize_input(field.data)
        
        return True
    
    def get_errors_dict(self):
        """Get all form errors as a dictionary."""
        errors = {}
        for field_name, field_errors in self.errors.items():
            errors[field_name] = field_errors
        return errors


def client_validation_schema(form):
    """Render the same basic rules for templates that hand-write their inputs."""
    schema = {}
    fields = getattr(form, '_fields', {})
    for name, field in fields.items():
        if field.type in ('CSRFTokenField','HiddenField','SubmitField'): continue
        attrs = {key.replace('_','-'):value for key,value in (field.render_kw or {}).items()
                 if key in ('type','min','max','step','minlength','maxlength','pattern','title') or key.startswith('data-')}
        if field.flags.required: attrs['required'] = True
        if field.type == 'EmailField': attrs['type'] = 'email'
        if field.type in CLIENT_INPUT_TYPES: attrs.setdefault('type',CLIENT_INPUT_TYPES[field.type])
        if attrs: schema[name] = attrs
    return {'anchor':next((name for name in fields if name in schema),''), 'fields':schema}
