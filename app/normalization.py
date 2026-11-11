"""Stable normalization shared by validation, models, and migrations."""
import re
import unicodedata


def clean_text(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').split())


def purok_identity(value):
    name = clean_text(value)
    match = re.fullmatch(r'purok[\s#.-]*(\d+)', name, re.I)
    number = int(match.group(1)) if match else None
    if number is not None:
        if not 1 <= number <= 9999:
            raise ValueError('Purok number must be between 1 and 9999.')
        name = f'Purok {number}'
    if not 2 <= len(name) <= 100:
        raise ValueError('Purok name must be 2–100 characters.')
    if not re.fullmatch(r'[A-Za-z0-9 .-]+', name):
        raise ValueError('Use letters, numbers, spaces, periods, and hyphens in Purok names.')
    return name, name.lower(), number
