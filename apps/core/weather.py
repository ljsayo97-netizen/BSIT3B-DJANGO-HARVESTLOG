"""Automatic farm weather for the dashboard.

Weather is resolved from the signed-in user's farm: the farm location is
geocoded once, then cached, and Open-Meteo's forecast endpoint is queried with
a short cache so dashboard visits stay fast and keep working when the API is
unreachable.

Open-Meteo is free and does not require an API key.
"""

import hashlib
import json
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

from apps.farms.models import Farm


GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'

DEFAULT_LOCATION_NAME = 'Manila, Philippines'
DEFAULT_LATITUDE = 14.5995
DEFAULT_LONGITUDE = 120.9842

CACHE_PREFIX = 'harvestlog:weather'

# WMO weather interpretation codes used by Open-Meteo.
# code: (label, daytime icon, night-time icon, tone)
WEATHER_CODES = {
    0: ('Clear sky', 'fas fa-sun', 'fas fa-moon', 'warning'),
    1: ('Mainly clear', 'fas fa-sun', 'fas fa-moon', 'warning'),
    2: ('Partly cloudy', 'fas fa-cloud-sun', 'fas fa-cloud-moon', 'secondary'),
    3: ('Overcast', 'fas fa-cloud', 'fas fa-cloud', 'secondary'),
    45: ('Fog', 'fas fa-smog', 'fas fa-smog', 'secondary'),
    48: ('Rime fog', 'fas fa-smog', 'fas fa-smog', 'secondary'),
    51: ('Light drizzle', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    53: ('Drizzle', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    55: ('Heavy drizzle', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    56: ('Freezing drizzle', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    57: ('Freezing drizzle', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    61: ('Light rain', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    63: ('Rain', 'fas fa-cloud-rain', 'fas fa-cloud-rain', 'info'),
    65: ('Heavy rain', 'fas fa-cloud-showers-heavy', 'fas fa-cloud-showers-heavy', 'danger'),
    66: ('Freezing rain', 'fas fa-cloud-showers-heavy', 'fas fa-cloud-showers-heavy', 'danger'),
    67: ('Freezing rain', 'fas fa-cloud-showers-heavy', 'fas fa-cloud-showers-heavy', 'danger'),
    71: ('Light snow', 'fas fa-snowflake', 'fas fa-snowflake', 'info'),
    73: ('Snow', 'fas fa-snowflake', 'fas fa-snowflake', 'info'),
    75: ('Heavy snow', 'fas fa-snowflake', 'fas fa-snowflake', 'danger'),
    77: ('Snow grains', 'fas fa-snowflake', 'fas fa-snowflake', 'info'),
    80: ('Light showers', 'fas fa-cloud-sun-rain', 'fas fa-cloud-moon-rain', 'info'),
    81: ('Showers', 'fas fa-cloud-showers-heavy', 'fas fa-cloud-showers-heavy', 'info'),
    82: ('Heavy showers', 'fas fa-cloud-showers-heavy', 'fas fa-cloud-showers-heavy', 'danger'),
    85: ('Snow showers', 'fas fa-snowflake', 'fas fa-snowflake', 'info'),
    86: ('Heavy snow showers', 'fas fa-snowflake', 'fas fa-snowflake', 'danger'),
    95: ('Thunderstorm', 'fas fa-cloud-bolt', 'fas fa-cloud-bolt', 'danger'),
    96: ('Thunderstorm with hail', 'fas fa-cloud-bolt', 'fas fa-cloud-bolt', 'danger'),
    99: ('Severe thunderstorm', 'fas fa-cloud-bolt', 'fas fa-cloud-bolt', 'danger'),
}


def _setting(name, default):
    return getattr(settings, name, default)


def _request_json(url, params, timeout=None):
    """Fetch and decode a JSON response from an Open-Meteo endpoint."""
    query = urlencode(params)
    request = Request(
        f'{url}?{query}',
        headers={
            'Accept': 'application/json',
            'User-Agent': 'HarvestLog/1.0 (farm dashboard weather)',
        },
    )
    if timeout is None:
        timeout = _setting('WEATHER_REQUEST_TIMEOUT', 6)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _cache_key(kind, value):
    digest = hashlib.md5(value.encode('utf-8')).hexdigest()
    return f'{CACHE_PREFIX}:{kind}:{digest}'


def _number(value, digits=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits)


def _format_time(value):
    """Format an Open-Meteo local timestamp, e.g. ``10:00`` -> ``10:00 AM``."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return ''
    hour = moment.hour % 12 or 12
    suffix = 'AM' if moment.hour < 12 else 'PM'
    return f'{hour}:{moment.minute:02d} {suffix}'


def describe_weather(code, is_day=True):
    """Return display metadata for a WMO weather code."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = -1
    label, day_icon, night_icon, tone = WEATHER_CODES.get(
        code,
        ('Unknown conditions', 'fas fa-cloud', 'fas fa-cloud', 'secondary'),
    )
    return {
        'code': code,
        'label': label,
        'icon': day_icon if is_day else night_icon,
        'tone': tone,
    }


def _display_name(result, query=''):
    name = (result.get('name') or '').strip()
    query = (query or '').strip()
    if (
        query
        and name.lower().startswith(query.lower())
        and len(name) > len(query)
    ):
        # Prefer the searched place name over a landmark suffix, e.g.
        # "Kabankalan City Public Plaza" becomes "Kabankalan City".
        name = query

    parts = []
    for value in (name, result.get('admin1'), result.get('country')):
        value = (value or '').strip()
        if value and value not in parts:
            parts.append(value)
    return ', '.join(parts) or 'Farm location'


def _preferred_result(results, query):
    """Pick the best geocoding result, preferring the configured country."""
    country = (_setting('WEATHER_COUNTRY_CODE', 'PH') or '').upper()
    if not country:
        return results[0] if results else None

    for result in results:
        if (result.get('country_code') or '').upper() == country:
            return result

    # An explicitly named country in the farm location overrides the default.
    lowered = query.lower()
    for result in results:
        country_name = (result.get('country') or '').lower()
        if country_name and country_name in lowered:
            return result

    # Do not guess with a match from the wrong country; the caller falls back
    # to the configured default location instead.
    return None


def _location_variants(query):
    """Build simpler searches from a detailed free-text farm location.

    Farm locations are often written as ``Barangay, City, Province``. Open-Meteo
    only recognises place names, so also try the city or municipality (usually
    the second-to-last comma-separated part).
    """
    variants = [query]
    parts = [part.strip() for part in query.split(',') if part.strip()]
    if len(parts) > 1:
        variants.append(parts[-2])

    unique = []
    seen = set()
    for variant in variants:
        key = variant.lower()
        if key not in seen and len(variant) >= 3:
            seen.add(key)
            unique.append(variant)
    return unique


def geocode_location(location):
    """Resolve a free-text farm location to coordinates (cached)."""
    query = (location or '').strip()
    if len(query) < 3:
        return None

    key = _cache_key('geocode', query.lower())
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    success_ttl = _setting('WEATHER_GEOCODE_CACHE_SECONDS', 60 * 60 * 24 * 30)
    failure_ttl = _setting('WEATHER_FAILURE_CACHE_SECONDS', 300)
    timeout = _setting('WEATHER_GEOCODE_TIMEOUT', 10)

    result = None
    matched = query
    for variant in _location_variants(query):
        try:
            payload = _request_json(
                GEOCODING_URL,
                {
                    'name': variant,
                    'count': 5,
                    'language': 'en',
                    'format': 'json',
                },
                timeout=timeout,
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            cache.set(key, {}, failure_ttl)
            return None

        result = _preferred_result(payload.get('results') or [], variant)
        if result:
            matched = variant
            break

    if not result:
        cache.set(key, {}, success_ttl)
        return None

    resolved = {
        'name': _display_name(result, matched),
        'latitude': _number(result.get('latitude'), 4),
        'longitude': _number(result.get('longitude'), 4),
        'country_code': (result.get('country_code') or '').upper(),
    }
    cache.set(key, resolved, success_ttl)
    return resolved


def _daily_row(index, values, is_day=True):
    code = values.get('weather_code')
    meta = describe_weather(code, is_day=is_day)

    raw_date = values.get('date')
    date_value = None
    if isinstance(raw_date, date):
        date_value = raw_date
    elif raw_date:
        try:
            date_value = date.fromisoformat(str(raw_date)[:10])
        except (TypeError, ValueError):
            date_value = None

    if index == 0:
        day_label = 'Today'
    elif index == 1:
        day_label = 'Tomorrow'
    elif date_value:
        day_label = date_value.strftime('%a')
    else:
        day_label = ''

    return {
        'date': date_value,
        'day_label': day_label,
        'date_label': date_value.strftime('%b %d') if date_value else '',
        'max': _number(values.get('temperature_2m_max')),
        'min': _number(values.get('temperature_2m_min')),
        'rain_probability': _number(
            values.get('precipitation_probability_max')
        ),
        'rain_sum': _number(values.get('precipitation_sum'), 1),
        'wind_max': _number(values.get('wind_speed_10m_max')),
        **meta,
    }


def _parse_forecast(payload):
    """Turn an Open-Meteo forecast payload into template-friendly data."""
    current = payload.get('current') or {}
    daily = payload.get('daily') or {}
    times = daily.get('time') or []

    days = []
    for index, raw_date in enumerate(times):
        values = {
            'date': raw_date,
            'weather_code': _index(daily.get('weather_code'), index),
            'temperature_2m_max': _index(
                daily.get('temperature_2m_max'), index
            ),
            'temperature_2m_min': _index(
                daily.get('temperature_2m_min'), index
            ),
            'precipitation_probability_max': _index(
                daily.get('precipitation_probability_max'), index
            ),
            'precipitation_sum': _index(
                daily.get('precipitation_sum'), index
            ),
            'wind_speed_10m_max': _index(
                daily.get('wind_speed_10m_max'), index
            ),
        }
        days.append(_daily_row(index, values))

    if not days:
        return None

    is_day = bool(current.get('is_day', 1))
    meta = describe_weather(current.get('weather_code'), is_day=is_day)
    current_data = {
        'temperature': _number(current.get('temperature_2m'), 1),
        'apparent': _number(current.get('apparent_temperature'), 1),
        'humidity': _number(current.get('relative_humidity_2m')),
        'wind': _number(current.get('wind_speed_10m')),
        'gusts': _number(current.get('wind_gusts_10m')),
        'precipitation': _number(current.get('precipitation'), 1),
        'is_day': is_day,
        'observed_at': _format_time(current.get('time')),
        **meta,
    }
    return {
        'current': current_data,
        'daily': days,
        'timezone': payload.get('timezone') or '',
    }


def _index(values, index):
    if isinstance(values, (list, tuple)) and index < len(values):
        return values[index]
    return None


def fetch_forecast(latitude, longitude):
    """Fetch and cache the forecast for one coordinate pair."""
    key = _cache_key('forecast', f'{latitude:.4f},{longitude:.4f}')
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    success_ttl = _setting('WEATHER_CACHE_SECONDS', 1800)
    failure_ttl = _setting('WEATHER_FAILURE_CACHE_SECONDS', 300)

    params = {
        'latitude': latitude,
        'longitude': longitude,
        'current': ','.join([
            'temperature_2m',
            'relative_humidity_2m',
            'apparent_temperature',
            'is_day',
            'precipitation',
            'weather_code',
            'wind_speed_10m',
            'wind_gusts_10m',
        ]),
        'daily': ','.join([
            'weather_code',
            'temperature_2m_max',
            'temperature_2m_min',
            'precipitation_probability_max',
            'precipitation_sum',
            'wind_speed_10m_max',
        ]),
        'timezone': 'auto',
        'forecast_days': 5,
    }

    try:
        payload = _request_json(FORECAST_URL, params)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        cache.set(key, {}, failure_ttl)
        return None

    forecast = _parse_forecast(payload)
    if forecast is None:
        cache.set(key, {}, failure_ttl)
        return None

    cache.set(key, forecast, success_ttl)
    return forecast


def _build_advice(current, daily):
    """Turn the forecast into short, actionable farm-work guidance."""
    today = daily[0] if daily else {}
    tomorrow = daily[1] if len(daily) > 1 else {}
    advice = []

    rain_probability = today.get('rain_probability') or 0
    rain_sum = today.get('rain_sum') or 0
    wind = today.get('wind_max') or 0
    high = today.get('max')
    humidity = current.get('humidity')
    temperature = current.get('temperature')

    if rain_probability >= 70 or rain_sum >= 10:
        advice.append({
            'tone': 'danger',
            'icon': 'fas fa-cloud-showers-heavy',
            'title': 'Heavy rain expected today',
            'text': (
                'Delay spraying, fertilizer application, and harvest work. '
                'Check field drainage and protect harvested produce.'
            ),
        })
    elif rain_probability >= 40 or rain_sum >= 2:
        advice.append({
            'tone': 'warning',
            'icon': 'fas fa-cloud-rain',
            'title': 'Showers likely today',
            'text': (
                'Plan field work around the rain. Skip irrigation and '
                'avoid spraying while the foliage is wet.'
            ),
        })

    if high is not None and high >= 35:
        advice.append({
            'tone': 'danger',
            'icon': 'fas fa-temperature-high',
            'title': 'Heat stress risk',
            'text': (
                'Irrigate early morning or late afternoon and avoid '
                'midday field work.'
            ),
        })
    elif (
        high is not None
        and high >= 33
        and rain_probability < 25
    ):
        advice.append({
            'tone': 'warning',
            'icon': 'fas fa-sun',
            'title': 'Hot and dry',
            'text': 'Check soil moisture and irrigate sensitive crops.',
        })

    if wind >= 30:
        advice.append({
            'tone': 'warning',
            'icon': 'fas fa-wind',
            'title': 'Strong winds',
            'text': (
                'Avoid spraying to prevent drift and secure stakes, nets, '
                'and young plants.'
            ),
        })

    if (
        humidity is not None
        and humidity >= 85
        and temperature is not None
        and 20 <= temperature <= 32
    ):
        advice.append({
            'tone': 'warning',
            'icon': 'fas fa-virus',
            'title': 'High disease pressure',
            'text': (
                'Humid conditions favor fungal disease. Inspect leaves and '
                'improve airflow between plants.'
            ),
        })

    if (
        not advice
        and tomorrow.get('rain_probability') is not None
        and tomorrow.get('rain_probability') >= 70
    ):
        advice.append({
            'tone': 'info',
            'icon': 'fas fa-calendar-day',
            'title': 'Rain expected tomorrow',
            'text': (
                'Move spraying, fertilizer application, and harvest '
                'preparation ahead of the rain.'
            ),
        })

    if not advice:
        advice.append({
            'tone': 'success',
            'icon': 'fas fa-check-circle',
            'title': 'Good field conditions',
            'text': 'Weather looks favorable for scheduled farm work.',
        })

    return advice[:3]


def _primary_farm(user):
    farms = Farm.objects.filter(user=user)
    return (
        farms.filter(status=Farm.Status.ACTIVE).order_by('name').first()
        or farms.order_by('name').first()
    )


def _resolve_location(farm):
    if farm is not None and farm.location:
        resolved = geocode_location(farm.location)
        if resolved:
            return {
                'name': resolved['name'],
                'latitude': resolved['latitude'],
                'longitude': resolved['longitude'],
                'farm_name': farm.name,
                'is_default': False,
            }

    return {
        'name': _setting(
            'WEATHER_DEFAULT_LOCATION_NAME', DEFAULT_LOCATION_NAME
        ),
        'latitude': _setting('WEATHER_DEFAULT_LATITUDE', DEFAULT_LATITUDE),
        'longitude': _setting('WEATHER_DEFAULT_LONGITUDE', DEFAULT_LONGITUDE),
        'farm_name': farm.name if farm is not None else '',
        'is_default': True,
    }


def build_weather_widget(user):
    """Return everything the dashboard weather widget needs."""
    farm = _primary_farm(user)
    location = _resolve_location(farm)
    forecast = fetch_forecast(
        location['latitude'], location['longitude']
    )
    if forecast is None:
        return {
            'available': False,
            'location': location,
            'source': 'Open-Meteo',
            'source_url': 'https://open-meteo.com/',
        }

    return {
        'available': True,
        'location': location,
        'current': forecast['current'],
        'daily': forecast['daily'][:4],
        'advice': _build_advice(
            forecast['current'], forecast['daily']
        ),
        'source': 'Open-Meteo',
        'source_url': 'https://open-meteo.com/',
    }
