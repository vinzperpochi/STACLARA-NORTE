"""Shared, optional resident registration details for existing records."""
from datetime import date

from flask import request
from flask_wtf.file import FileAllowed, FileField
from wtforms import StringField, SelectField, SelectMultipleField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.registration import EDUCATION, RELATIONSHIPS, DURATIONS, CATEGORIES
from .common import BaseForm, validate_phone_number


class ProfileDetailsForm(BaseForm):
    nationality = StringField('Nationality', default='Filipino', validators=[Optional(), Length(max=80)])
    place_of_birth = StringField('Place of birth', validators=[Optional(), Length(max=200)])
    religion = StringField('Religion (optional)', validators=[Optional(), Length(max=100)])
    educational_attainment = SelectField('Educational attainment', choices=EDUCATION, validators=[Optional()])
    household_relationship = SelectField('Relationship to household head', choices=RELATIONSHIPS, validators=[Optional()])
    house_no = StringField('House no. / lot / block', validators=[Optional(), Length(max=100)])
    street_landmark = StringField('Street / sitio / landmark', validators=[Optional(), Length(max=155)])
    residency_duration = SelectField('Duration of residency', choices=DURATIONS, validators=[Optional()])
    emergency_contact_name = StringField('Emergency contact name', validators=[Optional(), Length(max=200)])
    emergency_contact_relationship = StringField('Emergency contact relationship', validators=[Optional(), Length(max=80)])
    emergency_contact_number = StringField('Emergency contact number', validators=[Optional(), Length(max=30), validate_phone_number])
    special_categories = SelectMultipleField('Self-declared categories', choices=CATEGORIES, validators=[Optional()])
    profile_photo = FileField('Profile photo', validators=[Optional(), FileAllowed(['jpg','jpeg','png','webp'], 'Use JPEG, PNG or WebP for the profile photo.')])
    proof_of_residency = FileField('Proof of residency', validators=[Optional(), FileAllowed(['jpg','jpeg','png'], 'Use a JPEG or PNG image.')])
    philsys_card = FileField('PhilSys image (optional)', validators=[Optional(), FileAllowed(['jpg','jpeg','png'], 'Use a JPEG or PNG image.')])

    def __init__(self, *args, **kwargs):
        self._resident_birth_date = getattr(kwargs.get('obj'), 'birth_date', None)
        super().__init__(*args, **kwargs)
        self.emergency_contact_name.render_kw['data-required-with'] = 'emergency_contact_number'
        self.emergency_contact_number.render_kw['data-required-with'] = 'emergency_contact_name'
        self.special_categories.render_kw.update({'data-min-age':'60','data-age-value':'senior',
            'data-resident-birth-date':self._resident_birth_date.isoformat() if self._resident_birth_date else ''})

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)
        # Cross-field checks must also run when Optional skips a blank field.
        name = (self.emergency_contact_name.data or '').strip()
        number = (self.emergency_contact_number.data or '').strip()
        if number and not name:
            self.emergency_contact_name.errors.append('Enter the emergency contact name.')
            valid = False
        if name and not number:
            self.emergency_contact_number.errors.append('Enter the emergency contact number.')
            valid = False
        return valid

    def validate_special_categories(self, field):
        birth_date = self.birth_date.data if hasattr(self, 'birth_date') else self._resident_birth_date
        if 'senior' in (field.data or []) and birth_date:
            today = date.today()
            age = today.year - birth_date.year - ((today.month,today.day) < (birth_date.month,birth_date.day))
            if age < 60:
                raise ValidationError('Senior Citizen classification requires an age of at least 60.')

    def populate_obj(self, obj):
        # Uploaded files are stored transactionally, never assigned as model data.
        # Older partial POSTs must not erase fields absent from that submission.
        from app.normalization import clean_text
        from app.registration import PROFILE_FIELDS
        extended = set(PROFILE_FIELDS + ['nationality', 'special_categories'])
        for name, field in self._fields.items():
            if name not in obj.__mapper__.columns or isinstance(field, FileField):
                continue
            if name in extended and name not in request.form and not request.form.get('profile_details_present'):
                continue
            value = field.data
            if isinstance(value, str):
                value = clean_text(value) or None
            if name == 'nationality' and not value:
                value = obj.nationality or 'Filipino'
            setattr(obj, name, value)


class ProfileDetailsRequestForm(ProfileDetailsForm):
    reason = TextAreaField('Dahilan / paliwanag', validators=[DataRequired(), Length(min=10,max=500)],
                           default='Kinukumpleto ko ang aking registration details.')
