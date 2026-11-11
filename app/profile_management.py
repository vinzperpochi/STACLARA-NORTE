"""Account-owned profile presentation and explicit editable field boundaries."""
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import current_app
from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import Length, Optional
from app.forms.common import validate_phone_number
from app.forms.common import BaseForm


class ProfileContactForm(BaseForm):
    contact_number = StringField('Official contact number', validators=[Optional(), Length(max=30), validate_phone_number])
    emergency_contact_name = StringField('Emergency contact name', validators=[Optional(), Length(max=200)])
    emergency_contact_relationship = StringField('Relationship', validators=[Optional(), Length(max=80)])
    emergency_contact_number = StringField('Emergency contact number', validators=[Optional(), Length(max=30), validate_phone_number])


def profile_context(user):
    resident, official = user.resident, user.official
    # Staff replacements update the resident record; this is the canonical photo.
    photo = (resident.profile_photo_filename if resident else None) or user.profile_photo_filename
    if official:
        name = official.full_name
        required = [('Full name', official.full_name), ('Position', official.position), ('Contact number', official.contact_number), ('Email', user.email), ('Profile photo', photo)]
    elif resident:
        name = ' '.join(filter(None, [resident.first_name, resident.middle_name, resident.last_name, resident.suffix]))
        required = [('Full name', name), ('Birth date', resident.birth_date), ('Sex', resident.sex), ('Civil status', resident.civil_status), ('Nationality', resident.nationality), ('Address', resident.address_line), ('Contact number', resident.contact_number), ('Email', resident.email or user.email), ('Profile photo', photo)]
    else:
        name = user.username
        required = [('Username', user.username), ('Email', user.email), ('Profile photo', photo)]
    today = datetime.now(ZoneInfo(current_app.config['SYSTEM_TIMEZONE'])).date()
    age = today.year-resident.birth_date.year-((today.month,today.day)<(resident.birth_date.month,resident.birth_date.day)) if resident and resident.birth_date else None
    return dict(profile_name=name, profile_initials=''.join(part[0] for part in name.split()[:2]).upper(), profile_has_photo=bool(photo), profile_completeness=round(100*sum(bool(value) for _,value in required)/len(required)), profile_missing=[label for label,value in required if not value], profile_age=age)
