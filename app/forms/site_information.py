"""Validation for administrator-published contact and office details."""
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp
from .common import BaseForm, validate_email_format, validate_phone_number


class BarangayInformationForm(BaseForm):
    barangay_name = StringField('Barangay name',validators=[DataRequired(),Length(max=150)])
    municipality = StringField('Municipality',validators=[DataRequired(),Length(max=100)])
    province = StringField('Province',validators=[DataRequired(),Length(max=100)])
    country = StringField('Country',validators=[DataRequired(),Length(max=100)])
    zip_code = StringField('Postal code',validators=[Optional(),Regexp(r'^\d{4}$',message='Enter a four-digit postal code.')])
    hall_address = StringField('Exact barangay hall address',validators=[Optional(),Length(max=500)])
    contact_phone = StringField('Barangay office phone / hotline',validators=[Optional(),Length(max=30),validate_phone_number])
    contact_email = StringField('Barangay office email',validators=[Optional(),Length(max=255),validate_email_format])
    office_hours = StringField('Confirmed office hours',validators=[Optional(),Length(max=300)])
    dpo_name = StringField('Official DPO name',validators=[Optional(),Length(max=200)])
    dpo_email = StringField('Official DPO email',validators=[Optional(),Length(max=255),validate_email_format])
    dpo_phone = StringField('Official DPO phone',validators=[Optional(),Length(max=30),validate_phone_number])
    help_note = TextAreaField('Walk-in assistance',validators=[Optional(),Length(max=2000)])
    charter_note = TextAreaField('Citizen’s Charter information',validators=[Optional(),Length(max=2000)])
    fees_note = TextAreaField('Service-fee information',validators=[Optional(),Length(max=2000)])
    foi_note = TextAreaField('Information-request instructions',validators=[Optional(),Length(max=2000)])
