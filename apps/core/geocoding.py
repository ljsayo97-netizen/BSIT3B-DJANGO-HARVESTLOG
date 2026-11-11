"""Hierarchy-aware geocoding for Philippine farm addresses.

Farm locations are stored as free text, usually in the form
``Barangay, Municipality/City, Province``. A barangay name on its own is
ambiguous: "Vista Alegre", for example, exists in both Ilog and Bacolod.
This module therefore searches the full address hierarchy and only accepts a
result whose administrative area matches the requested municipality and
province.

Nominatim (OpenStreetMap) is used because its results include the
administrative address components needed for that validation. Results are
cached to keep farm-detail requests fast and to respect Nominatim's request
policy. When OSM has a barangay boundary, its outline is returned as well so
the Farm Field mini map can show the exact barangay area.
"""

import hashlib
import json
import re
import time
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

NOMINATIM_SEARCH_URL = 'https://nominatim.openstreetmap.org/search'
CACHE_PREFIX = 'harvestlog:geocode:v3'
DEFAULT_COUNTRY_CODE = 'PH'
COUNTRY_ALIASES = {'ph', 'philippines', 'pilipinas'}
MIN_NAME_SIMILARITY = 0.82
DEFAULT_USER_AGENT = 'HarvestLog/1.0 (farm location lookup)'

BARANGAY_PREFIX_RE = re.compile(
    r'^(?:brgy\.?|barangay|bgy\.?)\s*', re.IGNORECASE
)
LOCALITY_LABEL_RE = re.compile(
    r'^(?:purok|sitio|zone|block|lot|phase)\b', re.IGNORECASE
)
CITY_SUFFIX_RE = re.compile(r'\b(?:city|municipality)\s*$', re.IGNORECASE)
TRAILING_CITY_RE = re.compile(r'\b(?:city|municipality)\s*$', re.IGNORECASE)
LEADING_GENERIC_RE = re.compile(
    r'^(?:city|municipality|province)\s+of\s+', re.IGNORECASE
)
POSTAL_CODE_RE = re.compile(r'^\d{4,5}$')
NUMERIC_BARANGAY_RE = re.compile(r'^\d+[a-z]?(?:-\d+)?$', re.IGNORECASE)

# Province names let the parser recover addresses such as
# "Vista Alegre, Ilog Negros Occidental" where the municipality and province
# were written without a comma between them.
PROVINCE_NAMES = (
    'Abra',
    'Agusan del Norte',
    'Agusan del Sur',
    'Aklan',
    'Albay',
    'Antique',
    'Apayao',
    'Aurora',
    'Basilan',
    'Bataan',
    'Batanes',
    'Batangas',
    'Benguet',
    'Biliran',
    'Bohol',
    'Bukidnon',
    'Bulacan',
    'Cagayan',
    'Camarines Norte',
    'Camarines Sur',
    'Camiguin',
    'Capiz',
    'Catanduanes',
    'Cavite',
    'Cebu',
    'Cotabato',
    'Davao de Oro',
    'Davao del Norte',
    'Davao del Sur',
    'Davao Occidental',
    'Davao Oriental',
    'Dinagat Islands',
    'Eastern Samar',
    'Guimaras',
    'Ifugao',
    'Ilocos Norte',
    'Ilocos Sur',
    'Iloilo',
    'Isabela',
    'Kalinga',
    'La Union',
    'Laguna',
    'Lanao del Norte',
    'Lanao del Sur',
    'Leyte',
    'Maguindanao del Norte',
    'Maguindanao del Sur',
    'Marinduque',
    'Masbate',
    'Misamis Occidental',
    'Misamis Oriental',
    'Mountain Province',
    'Negros Occidental',
    'Negros Oriental',
    'Northern Samar',
    'Nueva Ecija',
    'Nueva Vizcaya',
    'Occidental Mindoro',
    'Oriental Mindoro',
    'Palawan',
    'Pampanga',
    'Pangasinan',
    'Quezon',
    'Quirino',
    'Rizal',
    'Romblon',
    'Samar',
    'Sarangani',
    'Siquijor',
    'Sorsogon',
    'South Cotabato',
    'Southern Leyte',
    'Sultan Kudarat',
    'Sulu',
    'Surigao del Norte',
    'Surigao del Sur',
    'Tarlac',
    'Tawi-Tawi',
    'Zambales',
    'Zamboanga del Norte',
    'Zamboanga del Sur',
    'Zamboanga Sibugay',
    'Compostela Valley',
    'Negros Island Region',
)

MUNICIPALITY_KEYS = (
    'city',
    'town',
    'municipality',
    'county',
    'district',
    'city_district',
)
PROVINCE_KEYS = ('state', 'province', 'region', 'state_district')

BARANGAY_PLACE_TYPES = {
    'village',
    'hamlet',
    'quarter',
    'neighbourhood',
    'neighborhood',
    'suburb',
    'isolated_dwelling',
}
BARANGAY_ADDRESS_KEYS = (
    'village',
    'hamlet',
    'quarter',
    'neighbourhood',
    'neighborhood',
    'suburb',
    'isolated_dwelling',
)
MUNICIPALITY_PLACE_TYPES = {
    'city',
    'town',
    'municipality',
    'administrative',
}

_last_request_at = 0.0


def _setting(name, default):
    return getattr(settings, name, default)


def normalize_place_name(value):
    """Normalize a place name for tolerant comparison."""
    text = (value or '').strip().lower()
    text = BARANGAY_PREFIX_RE.sub('', text)
    text = LEADING_GENERIC_RE.sub('', text)
    text = TRAILING_CITY_RE.sub('', text)
    text = re.sub(r'[^a-z0-9\s-]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def place_names_match(expected, actual):
    """Return True when two place names refer to the same place.

    A fuzzy comparison lets common spelling mistakes such as
    "Negros Ociddental" still match the correct province, while short,
    unrelated names such as "Ilog" and "Iloilo" stay distinct.
    """
    expected_name = normalize_place_name(expected)
    actual_name = normalize_place_name(actual)
    if not expected_name or not actual_name:
        return False
    if expected_name == actual_name:
        return True
    return (
        SequenceMatcher(None, expected_name, actual_name).ratio()
        >= MIN_NAME_SIMILARITY
    )


def _barangay_name(value):
    name = BARANGAY_PREFIX_RE.sub('', (value or '').strip()).strip()
    return name or (value or '').strip()


def barangay_query_name(value):
    """Format a barangay for a Nominatim search.

    Bare names work best ("Vista Alegre"), except for numbered barangays,
    where Nominatim expects the "Barangay N" form.
    """
    name = _barangay_name(value)
    if not name:
        return ''
    if NUMERIC_BARANGAY_RE.match(name):
        return f'Barangay {name}'
    if LOCALITY_LABEL_RE.match(name):
        return ''
    return name


def _split_province_suffix(value):
    """Split "Ilog Negros Occidental" into municipality and province.

    A missing comma between the municipality and province is a common data
    entry mistake. Only split when a known province name appears at the end
    and at least one word remains for the municipality.
    """
    words = (value or '').split()
    if len(words) < 3:
        return None

    max_words = min(4, len(words) - 1)
    for count in range(max_words, 1, -1):
        candidate = ' '.join(words[-count:])
        for province in PROVINCE_NAMES:
            if place_names_match(province, candidate):
                municipality = ' '.join(words[:-count]).strip()
                if municipality:
                    return {
                        'municipality': municipality,
                        'province': province,
                    }
    return None


def parse_location(location):
    """Split a free-text Philippine address into address components.

    The expected order is ``Barangay, Municipality/City, Province``. Two-part
    addresses are treated as either ``barangay, municipality`` or
    ``municipality, province`` and both interpretations are kept so the
    geocoder can validate whichever one actually matches.
    """
    raw = (location or '').strip()
    parts = [part.strip() for part in raw.split(',') if part.strip()]

    if parts and normalize_place_name(parts[-1]) in COUNTRY_ALIASES:
        parts.pop()
    if parts and POSTAL_CODE_RE.match(parts[-1]):
        parts.pop()

    if parts:
        split = _split_province_suffix(parts[-1])
        if split:
            parts = parts[:-1] + [split['municipality'], split['province']]

    barangay = ''
    municipality = ''
    province = ''
    alternate = None

    if len(parts) == 1:
        municipality = parts[0]
    elif len(parts) == 2:
        first, second = parts
        looks_like_barangay = (
            CITY_SUFFIX_RE.search(second)
            or BARANGAY_PREFIX_RE.match(first)
            or LOCALITY_LABEL_RE.match(first)
        )
        if looks_like_barangay:
            barangay = _barangay_name(first)
            municipality = second
        else:
            municipality = first
            province = second
            alternate = {
                'barangay': _barangay_name(first),
                'municipality': second,
                'province': '',
            }
    elif len(parts) >= 3:
        province = parts[-1]
        municipality = parts[-2]
        locality_parts = parts[:-2]
        named_parts = [
            part for part in locality_parts
            if not LOCALITY_LABEL_RE.match(part)
        ]
        source = (named_parts or locality_parts)[-1]
        barangay = _barangay_name(source)

    return {
        'raw': raw,
        'parts': parts,
        'barangay': barangay,
        'municipality': municipality,
        'province': province,
        'alternate': alternate,
    }


def _candidate_queries(parsed):
    """Build hierarchical queries, most specific first.

    Each candidate carries the municipality/province values that a result
    must match. Expectations are merged when two interpretations produce the
    same query string.
    """
    candidates = []

    def add(query_parts, municipality, province):
        query = ', '.join(
            [part for part in query_parts if part] + ['Philippines']
        )
        if not query:
            return
        expectation = (municipality or '', province or '')
        for candidate in candidates:
            if candidate['query'].lower() == query.lower():
                if expectation not in candidate['expectations']:
                    candidate['expectations'].append(expectation)
                return
        candidates.append({
            'query': query,
            'expectations': [expectation],
        })

    barangay = barangay_query_name(parsed['barangay'])
    municipality = parsed['municipality']
    province = parsed['province']

    if barangay and municipality:
        if province:
            add(
                [barangay, municipality, province],
                municipality,
                province,
            )
        add([barangay, municipality], municipality, '')

    if municipality:
        if province:
            add([municipality, province], municipality, province)
        add([municipality], municipality, '')

    alternate = parsed.get('alternate')
    if alternate and alternate.get('municipality'):
        alternate_barangay = barangay_query_name(alternate.get('barangay'))
        alternate_municipality = alternate['municipality']
        if alternate_barangay:
            add(
                [alternate_barangay, alternate_municipality],
                alternate_municipality,
                '',
            )
        add([alternate_municipality], alternate_municipality, '')

    return candidates


def _result_address_values(result, keys):
    address = result.get('address') or {}
    return [address[key] for key in keys if address.get(key)]


def _matches_expectation(result, municipality, province):
    country_code = (
        (result.get('address') or {}).get('country_code')
        or result.get('country_code')
        or ''
    ).upper()
    expected_country = (
        _setting('WEATHER_COUNTRY_CODE', DEFAULT_COUNTRY_CODE) or ''
    ).upper()
    if expected_country and country_code and country_code != expected_country:
        return False

    if municipality:
        values = _result_address_values(result, MUNICIPALITY_KEYS)
        if not values or not any(
            place_names_match(municipality, value) for value in values
        ):
            return False

    if province:
        values = _result_address_values(result, PROVINCE_KEYS)
        if not values or not any(
            place_names_match(province, value) for value in values
        ):
            return False

    return True


def _result_matches(result, expectations):
    return any(
        _matches_expectation(result, municipality, province)
        for municipality, province in expectations
    )


def _result_display_name(result, parsed):
    address = result.get('address') or {}
    name = (result.get('name') or '').strip()
    municipality = (
        address.get('town')
        or address.get('city')
        or address.get('municipality')
        or parsed['municipality']
    )
    province = (
        address.get('state')
        or address.get('province')
        or parsed['province']
    )

    parts = []
    normalized_parts = set()
    for value in (name, municipality, province):
        value = (value or '').strip()
        if not value:
            continue
        normalized = normalize_place_name(value)
        if normalized and normalized not in normalized_parts:
            normalized_parts.add(normalized)
            parts.append(value)
    return ', '.join(parts) or parsed['raw'] or 'Farm location'


def _result_level(result, parsed):
    place_type = (
        result.get('addresstype') or result.get('type') or ''
    ).lower()
    if place_type in BARANGAY_PLACE_TYPES:
        return 'barangay'
    if place_type in MUNICIPALITY_PLACE_TYPES:
        return 'municipality'

    name = result.get('name') or ''
    if parsed['barangay'] and place_names_match(parsed['barangay'], name):
        return 'barangay'
    return 'approximate'


def _result_barangay_name(result):
    """Return the barangay name Nominatim actually matched."""
    address = result.get('address') or {}
    for key in BARANGAY_ADDRESS_KEYS:
        value = (address.get(key) or '').strip()
        if value:
            return _barangay_name(value)
    return ''


def _result_boundary(result):
    """Return the barangay outline when Nominatim provides one."""
    geojson = result.get('geojson')
    if not isinstance(geojson, dict):
        return None
    if geojson.get('type') not in ('Polygon', 'MultiPolygon'):
        return None
    if not geojson.get('coordinates'):
        return None
    return geojson


def _cache_key(kind, value):
    digest = hashlib.md5(value.encode('utf-8')).hexdigest()
    return f'{CACHE_PREFIX}:{kind}:{digest}'


def _number(value, digits=6):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits)


def _throttle():
    """Keep requests within Nominatim's one-request-per-second policy."""
    global _last_request_at
    interval = float(_setting('GEOCODING_MIN_INTERVAL_SECONDS', 1.0) or 0)
    if interval <= 0:
        return
    now = time.monotonic()
    wait = interval - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _request_json(url, params, timeout):
    query = urlencode(params)
    request = Request(
        f'{url}?{query}',
        headers={
            'Accept': 'application/json',
            'Accept-Language': 'en',
            'User-Agent': _setting(
                'GEOCODING_USER_AGENT', DEFAULT_USER_AGENT
            ),
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _nominatim_search(query, timeout=None):
    """Return Nominatim results for one query string."""
    _throttle()
    country = (
        _setting('WEATHER_COUNTRY_CODE', DEFAULT_COUNTRY_CODE) or ''
    ).lower()
    params = {
        'q': query,
        'format': 'jsonv2',
        'addressdetails': 1,
        'limit': 5,
        'dedupe': 1,
        'polygon_geojson': 1,
    }
    if country:
        params['countrycodes'] = country
    if timeout is None:
        timeout = _setting('WEATHER_GEOCODE_TIMEOUT', 10)
    payload = _request_json(NOMINATIM_SEARCH_URL, params, timeout)
    return payload if isinstance(payload, list) else []


def geocode_ph_location(location):
    """Resolve a Philippine farm address to coordinates (cached).

    Returns a dict with ``latitude``, ``longitude``, a human-readable
    ``name`` and the resolved administrative components. Returns ``None``
    when no result matches the requested hierarchy, rather than guessing a
    same-named place in another city.
    """
    parsed = parse_location(location)
    if not parsed['raw'] or len(parsed['raw']) < 3:
        return None

    key = _cache_key('nominatim', parsed['raw'].lower())
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    success_ttl = _setting(
        'WEATHER_GEOCODE_CACHE_SECONDS', 60 * 60 * 24 * 30
    )
    failure_ttl = _setting('WEATHER_FAILURE_CACHE_SECONDS', 300)
    timeout = _setting('WEATHER_GEOCODE_TIMEOUT', 10)

    for candidate in _candidate_queries(parsed):
        try:
            results = _nominatim_search(
                candidate['query'], timeout=timeout
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            cache.set(key, {}, failure_ttl)
            return None

        for result in results:
            if not _result_matches(result, candidate['expectations']):
                continue
            latitude = _number(result.get('lat'))
            longitude = _number(result.get('lon'))
            if latitude is None or longitude is None:
                continue

            level = _result_level(result, parsed)
            matched_barangay = _result_barangay_name(result)
            if not matched_barangay and level == 'barangay':
                matched_barangay = parsed['barangay']

            resolved = {
                'name': _result_display_name(result, parsed),
                'latitude': latitude,
                'longitude': longitude,
                'country_code': (
                    (result.get('address') or {}).get('country_code')
                    or result.get('country_code')
                    or ''
                ).upper(),
                'barangay': parsed['barangay'],
                'matched_barangay': matched_barangay,
                'barangay_boundary': _result_boundary(result),
                'municipality': (
                    (result.get('address') or {}).get('town')
                    or (result.get('address') or {}).get('city')
                    or (result.get('address') or {}).get('municipality')
                    or parsed['municipality']
                ),
                'province': (
                    (result.get('address') or {}).get('state')
                    or (result.get('address') or {}).get('province')
                    or parsed['province']
                ),
                'level': level,
                'source': 'nominatim',
                'query': candidate['query'],
            }
            cache.set(key, resolved, success_ttl)
            return resolved

    cache.set(key, {}, failure_ttl)
    return None
