"""Additive reader feedback codes; never make an attendance decision here."""


def error_voice_code(message, status=422):
    if status in (401, 403):
        return 'READER_SETUP'
    if status == 429:
        return 'REPEAT_TAP'
    prefixes = (
        ('Card already registered.', 'DUPLICATE_CARD'),
        ('Unregistered or revoked RFID card.', 'UNKNOWN_CARD'),
        ('Personnel account is inactive.', 'INACTIVE_ACCOUNT'),
        ('No active work schedule assigned.', 'NO_SCHEDULE'),
        ('No effective schedule for ', 'NO_SCHEDULE'),
        ('Not a scheduled work day:', 'NOT_DUTY_DAY'),
        ('Too early.', 'TOO_EARLY'),
        ('Outside schedule scan window:', 'OUTSIDE_SCHEDULE'),
        ('Open session exceeds 24 hours.', 'REVIEW_REQUIRED'),
        ('Already clocked in.', 'REVIEW_REQUIRED'),
        ('No open session to clock out.', 'REVIEW_REQUIRED'),
        ('Time Out must follow Time In.', 'REVIEW_REQUIRED'),
        ('Approved leave applies to this work date.', 'ON_LEAVE'),
        ('Repeated or out-of-order scan ignored.', 'REPEAT_TAP'),
        ('Maximum authorized work sessions reached.', 'SESSION_LIMIT'),
        ('Reader reserved for RFID registration.', 'REGISTRATION_MODE'),
        ('Reader is reserved for card registration.', 'REGISTRATION_MODE'),
    )
    for prefix, code in prefixes:
        if str(message).startswith(prefix):
            return code
    return 'OFFLINE_VOICE' if status >= 500 else 'GENERIC_ERROR'


def response_voice_code(endpoint, payload, status):
    if status >= 400 or payload.get('success') is False:
        if endpoint == 'attendance.registration_mode' and status == 409:
            return 'READER_SETUP'
        return error_voice_code(payload.get('message', ''), status)
    if endpoint == 'attendance.device_scan' and payload.get('success'):
        return 'TIME_IN_VOICE' if payload.get('action') == 'IN' else 'TIME_OUT_VOICE'
    if endpoint == 'attendance.registration_tap' and payload.get('success'):
        return 'CAPTURED'
    if endpoint == 'attendance.registration_mode':
        return 'READY'
    return 'PREVIEW_OK'
