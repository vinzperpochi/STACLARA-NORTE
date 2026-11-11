"""Reject malformed numeric inputs instead of silently substituting zero."""
import math
from flask import request

def strict_form_value(field, default=None, type=int):
    raw = request.form.get(field)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = type(raw)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field.replace('_', ' ').title()} must be a valid number.") from exc
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field.replace('_', ' ').title()} must be finite.")
    return value
