"""
Server-side proxy for Nominatim (OpenStreetMap geocoding).
Uses Python's standard library so the application can start without an
additional requests package dependency.
"""
from flask import Blueprint, request, jsonify, current_app
from urllib import parse, request as urllib_request, error as urllib_error
from time import time, sleep
import json

geocoding_bp = Blueprint('geocoding', __name__, url_prefix='/api/geocode')

# Module-level rate-limit state (per worker process)
_last_request_time = 0.0
_MIN_INTERVAL = 1.0  # Nominatim allows 1 req/sec


class GeocodingTimeout(Exception):
    """Raised when the Nominatim request exceeds its timeout."""


class GeocodingRequestError(Exception):
    """Raised for network or HTTP errors from Nominatim."""


def _rate_limited_get(url, params):
    """GET a Nominatim endpoint with rate limiting and a descriptive User-Agent."""
    global _last_request_time
    now = time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time()

    user_agent = current_app.config.get(
        'NOMINATIM_USER_AGENT', 'BarangayManagementSystem/1.0'
    )
    headers = {
        'User-Agent': user_agent,
        'Accept-Language': 'en',
        'Accept': 'application/json',
    }
    query = parse.urlencode(params)
    req = urllib_request.Request(f'{url}?{query}', headers=headers, method='GET')
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            status = getattr(response, 'status', 200)
            body = response.read()
    except urllib_error.URLError as exc:
        reason = getattr(exc, 'reason', None)
        if isinstance(reason, TimeoutError) or 'timed out' in str(exc).lower():
            raise GeocodingTimeout() from exc
        raise GeocodingRequestError(str(exc)) from exc
    except TimeoutError as exc:
        raise GeocodingTimeout() from exc

    if status >= 400:
        raise GeocodingRequestError(f'Nominatim returned HTTP {status}')
    try:
        return json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeocodingRequestError('Invalid response from Nominatim') from exc


@geocoding_bp.route('/search')
def search():
    """Forward geocoding: address string -> coordinates."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'q parameter is required'}), 400
    countrycodes = request.args.get('countrycodes', 'ph')
    limit = request.args.get('limit', '5')
    try:
        result = _rate_limited_get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'format': 'json',
                'q': q,
                'countrycodes': countrycodes,
                'limit': limit,
                'addressdetails': '1',
            },
        )
        return jsonify(result)
    except GeocodingTimeout:
        return jsonify({'error': 'Geocoding service timed out'}), 504
    except GeocodingRequestError as exc:
        current_app.logger.error('Nominatim search error: %s', exc)
        return jsonify({'error': 'Geocoding service unavailable'}), 502


@geocoding_bp.route('/reverse')
def reverse():
    """Reverse geocoding: coordinates -> address string."""
    lat = request.args.get('lat', '').strip()
    lon = request.args.get('lon', '').strip()
    if not lat or not lon:
        return jsonify({'error': 'lat and lon parameters are required'}), 400
    try:
        result = _rate_limited_get(
            'https://nominatim.openstreetmap.org/reverse',
            params={
                'format': 'json',
                'lat': lat,
                'lon': lon,
                'zoom': '18',
                'addressdetails': '1',
            },
        )
        return jsonify(result)
    except GeocodingTimeout:
        return jsonify({'error': 'Geocoding service timed out'}), 504
    except GeocodingRequestError as exc:
        current_app.logger.error('Nominatim reverse error: %s', exc)
        return jsonify({'error': 'Geocoding service unavailable'}), 502
