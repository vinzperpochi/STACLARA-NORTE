"""Common persistence validation for HTML, API and service entry points."""
from datetime import date, datetime, timezone
from decimal import Decimal
import math
from sqlalchemy import event, inspect, String, Numeric, Integer
from sqlalchemy.orm import Session
from app.normalization import clean_text


@event.listens_for(Session, 'before_flush')
def validate_entities(session, flush_context, instances):
    for obj in list(session.new) + list(session.dirty):
        if type(obj).__name__ in {'AuditLog', 'UserSession', 'LoginAttempt'}:
            continue
        if type(obj).__name__ == 'Purok':
            from app.normalization import purok_identity
            obj.name, obj.name_key, inferred = purok_identity(obj.name)
            if inferred is not None and obj.purok_number is None:
                obj.purok_number = inferred
        state = inspect(obj)
        for column in state.mapper.columns:
            value = getattr(obj, column.key)
            label = column.key.replace('_', ' ').capitalize()
            if value is None:
                # ORM/server defaults and relationships may populate missing values during flush.
                if not column.nullable and not column.primary_key and column.default is None and column.server_default is None and not column.foreign_keys:
                    raise ValueError(f'{label} is required.')
                continue
            if isinstance(column.type, String) and isinstance(value, str):
                if not column.nullable and not value.strip():
                    raise ValueError(f'{label} is required.')
                if column.type.length and len(value) > column.type.length:
                    raise ValueError(f'{label} must be at most {column.type.length} characters.')
            if isinstance(value, (float, Decimal)) and not math.isfinite(value):
                raise ValueError(f'{label} must be a finite number.')
            if isinstance(column.type, (Numeric, Integer)) and column.key not in {'incident_latitude', 'incident_longitude'} and not column.foreign_keys and not column.primary_key:
                if isinstance(value, (int, float, Decimal)) and value < 0:
                    raise ValueError(f'{label} cannot be negative.')
        if type(obj).__name__ == 'Resident':
            if obj.household_id:
                from app.models import Household
                household = session.get(Household, obj.household_id)
                if household is None:
                    raise ValueError('Household does not exist.')
                if obj.purok_id is None:
                    obj.purok_id = household.purok_id
                elif obj.purok_id != household.purok_id:
                    raise ValueError('Resident Purok must match the selected household.')
            for key in ('first_name', 'middle_name', 'last_name', 'suffix', 'contact_number', 'address_line'):
                value = getattr(obj, key)
                if value:
                    setattr(obj, key, clean_text(value))
            if obj.birth_date and (obj.birth_date > date.today() or obj.birth_date < date(1900, 1, 1)):
                raise ValueError('Birth date must be between 1900 and today.')
        if type(obj).__name__ == 'BusinessRecord':
            if obj.registration_date and obj.expiration_date and obj.expiration_date < obj.registration_date:
                raise ValueError('Expiration date cannot be before registration date.')
            if obj.status and obj.status.upper() not in {'ACTIVE', 'INACTIVE', 'EXPIRED', 'SUSPENDED', 'CLOSED'}:
                raise ValueError('Invalid business status.')
        if type(obj).__name__ == 'BlotterCase':
            if obj.incident_date and obj.incident_date > date.today():
                raise ValueError('Incident date cannot be in the future.')
            if (obj.incident_latitude is None) != (obj.incident_longitude is None):
                raise ValueError('Provide both incident coordinates.')
            if obj.incident_latitude is not None and (not -90 <= obj.incident_latitude <= 90 or not -180 <= obj.incident_longitude <= 180):
                raise ValueError('Invalid incident coordinates.')
        if type(obj).__name__ == 'Event' and obj.ends_at and obj.starts_at:
            def utc(value):
                return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
            if utc(obj.ends_at) < utc(obj.starts_at):
                raise ValueError('Event end must be after its start.')
