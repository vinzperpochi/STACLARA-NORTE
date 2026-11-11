"""Validation service for handling form validation, sanitization, and error formatting."""

import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime
from werkzeug.datastructures import FileStorage
from flask import flash, current_app
from wtforms import ValidationError as WTFormsValidationError

from app.forms.common import sanitize_input, ValidationError


class ValidationService:
    """Central validation service for all form processing."""
    
    @staticmethod
    def sanitize_input(value):
        """Sanitize input string - wrapper for the common sanitize_input function."""
        return sanitize_input(value) if value else value
    
    @staticmethod
    def handle_form_error(form, error_message):
        """Handle form errors by flashing appropriate messages."""
        flash(f"Error: {error_message}", "danger")
        # Also flash any existing form errors
        if hasattr(form, 'errors') and form.errors:
            ValidationService.flash_form_errors(form)
    
    @staticmethod
    def validate_form(form, flash_errors: bool = True) -> bool:
        """Validate a FlaskForm and optionally flash errors."""
        if hasattr(form, 'validate_and_sanitize'):
            is_valid = form.validate_and_sanitize()
        else:
            is_valid = form.validate()
        
        if not is_valid and flash_errors:
            ValidationService.flash_form_errors(form)
        
        return is_valid
    
    @staticmethod
    def flash_form_errors(form) -> None:
        """Flash all form validation errors."""
        for field_name, errors in form.errors.items():
            for error in errors:
                flash(f"{form[field_name].label.text}: {error}", "danger")
    
    @staticmethod
    def get_form_errors_dict(form) -> Dict[str, List[str]]:
        """Get form errors as a dictionary for JSON responses."""
        return {field: errors for field, errors in form.errors.items()}
    
    @staticmethod
    def validate_and_sanitize_dict(data: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Validate and sanitize a dictionary of data against rules.
        
        Args:
            data: Raw input data
            rules: Validation rules per field
            
        Returns:
            Tuple of (sanitized_data, errors)
        """
        sanitized = {}
        errors = []
        
        for field, rule in rules.items():
            value = data.get(field)
            
            try:
                # Apply sanitization
                if isinstance(value, str):
                    value = sanitize_input(value)
                
                # Apply validation rules
                if 'required' in rule and rule['required'] and not value:
                    errors.append(f"{field}: This field is required")
                    continue
                
                if value:  # Only validate non-empty values
                    if 'type' in rule:
                        value = ValidationService._validate_type(value, rule['type'], field)
                    
                    if 'min_length' in rule and len(str(value)) < rule['min_length']:
                        errors.append(f"{field}: Must be at least {rule['min_length']} characters")
                    
                    if 'max_length' in rule and len(str(value)) > rule['max_length']:
                        errors.append(f"{field}: Cannot exceed {rule['max_length']} characters")
                    
                    if 'pattern' in rule and not re.match(rule['pattern'], str(value)):
                        errors.append(f"{field}: {rule.get('pattern_message', 'Invalid format')}")
                    
                    if 'custom' in rule:
                        try:
                            rule['custom'](value)
                        except ValidationError as e:
                            errors.append(f"{field}: {e.message}")
                
                sanitized[field] = value
                
            except ValidationError as e:
                errors.append(f"{field}: {e.message}")
            except ValueError as e:
                errors.append(f"{field}: {str(e)}")
        
        return sanitized, errors
    
    @staticmethod
    def _validate_type(value: Any, expected_type: str, field_name: str) -> Any:
        """Validate and convert value to expected type."""
        if expected_type == 'int':
            if isinstance(value, str):
                if not value.strip().lstrip('-').isdigit():
                    raise ValidationError(f"Must be a number", field_name)
                return int(value)
            elif not isinstance(value, int):
                raise ValidationError(f"Must be a number", field_name)
        
        elif expected_type == 'float':
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Must be a decimal number", field_name)
        
        elif expected_type == 'date':
            if isinstance(value, str):
                try:
                    return datetime.strptime(value, '%Y-%m-%d').date()
                except ValueError:
                    raise ValidationError(f"Must be a valid date (YYYY-MM-DD)", field_name)
            elif not isinstance(value, date):
                raise ValidationError(f"Must be a date", field_name)
        
        elif expected_type == 'email':
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', str(value)):
                raise ValidationError(f"Must be a valid email address", field_name)
        
        elif expected_type == 'phone':
            phone = re.sub(r'\D', '', str(value))
            if not ((phone.startswith('09') and len(phone) == 11) or 
                   (phone.startswith('639') and len(phone) == 12) or
                   (len(phone) >= 7 and len(phone) <= 11)):
                raise ValidationError(f"Must be a valid Philippine phone number", field_name)
        
        return value
    
    @staticmethod
    def validate_file_upload(file: FileStorage, allowed_extensions: List[str] = None, 
                           max_size_mb: int = 5) -> List[str]:
        """Validate file upload and return any errors."""
        errors = []
        
        if not file or not file.filename:
            errors.append("No file selected")
            return errors
        
        # Check filename security
        if not re.match(r'^[a-zA-Z0-9._-]+$', file.filename):
            errors.append("Filename contains invalid characters")
        
        # Check extension
        if allowed_extensions:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext not in [e.lower() for e in allowed_extensions]:
                allowed_str = ', '.join(allowed_extensions)
                errors.append(f"Only these file types are allowed: {allowed_str}")
        
        # Check file size (approximate)
        if hasattr(file, 'content_length') and file.content_length:
            if file.content_length > max_size_mb * 1024 * 1024:
                errors.append(f"File size must be under {max_size_mb}MB")
        
        return errors
    
    @staticmethod
    def create_validation_rules() -> Dict[str, Dict[str, Any]]:
        """Create common validation rule sets for different form types."""
        return {
            'resident_personal': {
                'first_name': {
                    'required': True,
                    'min_length': 2,
                    'max_length': 100,
                    'pattern': r'^[a-zA-Z\s\-\.]+$',
                    'pattern_message': 'Only letters, spaces, hyphens, and periods allowed'
                },
                'last_name': {
                    'required': True,
                    'min_length': 2,
                    'max_length': 100,
                    'pattern': r'^[a-zA-Z\s\-\.]+$',
                    'pattern_message': 'Only letters, spaces, hyphens, and periods allowed'
                },
                'middle_name': {
                    'required': False,
                    'max_length': 100,
                    'pattern': r'^[a-zA-Z\s\-\.]*$',
                    'pattern_message': 'Only letters, spaces, hyphens, and periods allowed'
                },
                'email': {
                    'required': True,
                    'type': 'email',
                    'max_length': 255
                },
                'contact_number': {
                    'required': False,
                    'type': 'phone'
                },
                'birth_date': {
                    'required': False,
                    'type': 'date'
                }
            },
            'document_request': {
                'document_type_id': {
                    'required': True,
                    'type': 'int'
                },
                'description': {
                    'required': False,
                    'max_length': 500
                }
            },
            'blotter_case': {
                'respondent_name': {
                    'required': True,
                    'min_length': 2,
                    'max_length': 200
                },
                'category': {
                    'required': True
                },
                'narrative': {
                    'required': True,
                    'min_length': 20,
                    'max_length': 2000
                },
                'incident_date': {
                    'required': True,
                    'type': 'date'
                }
            }
        }


# Convenience functions for common validation scenarios
def validate_resident_form_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate resident registration/update data."""
    rules = ValidationService.create_validation_rules()['resident_personal']
    return ValidationService.validate_and_sanitize_dict(data, rules)


def validate_document_request_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate document request data."""
    rules = ValidationService.create_validation_rules()['document_request']
    return ValidationService.validate_and_sanitize_dict(data, rules)


def validate_blotter_case_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Validate blotter case data."""
    rules = ValidationService.create_validation_rules()['blotter_case']
    return ValidationService.validate_and_sanitize_dict(data, rules)