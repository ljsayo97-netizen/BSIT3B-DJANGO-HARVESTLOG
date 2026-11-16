"""Crop image retrieval service integrating Unsplash, Pexels, and Pixabay APIs.

Features:
- Queries official Unsplash, Pexels, and Pixabay APIs using environment keys.
- Maps crop names to realistic agricultural field keywords.
- Prioritizes realistic agricultural photographs and filters out cartoons/clipart.
- Provides graceful error handling and verified fallback catalog when API keys are absent or offline.
- Downloads selected photographs locally into Django's media storage and returns relative media path.
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path
from PIL import Image

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from .catalog import CROP_CATALOG, find_catalog_entry

logger = logging.getLogger(__name__)

# Official Search Keywords for Realistic Agricultural Photos
CROP_KEYWORD_MAP = {
    'rice': 'Rice plants growing in a field',
    'palay': 'Rice plants growing in a field',
    'corn': 'Fresh corn growing in a cornfield',
    'mais': 'Fresh corn growing in a cornfield',
    'tomato': 'Red tomatoes growing on a plant',
    'kamatis': 'Red tomatoes growing on a plant',
    'banana': 'Banana bunch growing on a tree',
    'saging': 'Banana bunch growing on a tree',
    'mango': 'Ripe mangoes on a tree',
    'mangga': 'Ripe mangoes on a tree',
    'grape': 'Ripe grapes growing on a vine in a vineyard',
    'grapes': 'Ripe grapes growing on a vine in a vineyard',
    'ubas': 'Ripe grapes growing on a vine in a vineyard',
    'sugarcane': 'Sugarcane plantation',
    'tubo': 'Sugarcane plantation',
    'peanut': 'Fresh peanuts growing in soil',
    'mani': 'Fresh peanuts growing in soil',
    'lettuce': 'Fresh green lettuce growing in a farm',
    'letsugas': 'Fresh green lettuce growing in a farm',
    'eggplant': 'Eggplants growing on a plant in farm',
    'talong': 'Eggplants growing on a plant in farm',
    'ampalaya': 'Bitter gourd growing on vine trellis farm',
    'bitter gourd': 'Bitter gourd growing on vine trellis farm',
    'pechay': 'Fresh green bok choy growing in farm',
    'okra': 'Fresh green okra pods growing on plant in farm',
    'cassava': 'Cassava plants growing in agricultural field',
    'kamoteng kahoy': 'Cassava plants growing in agricultural field',
    'sweet potato': 'Sweet potato vine crop growing in farm soil',
    'kamote': 'Sweet potato vine crop growing in farm soil',
    'watermelon': 'Fresh watermelons growing in a farm field',
    'pakwan': 'Fresh watermelons growing in a farm field',
    'melon': 'Cantaloupe melon growing in agricultural farm',
    'cucumber': 'Cucumbers growing on vine in farm',
    'pipino': 'Cucumbers growing on vine in farm',
    'squash': 'Squash pumpkins growing in farm field',
    'kalabasa': 'Squash pumpkins growing in farm field',
    'onion': 'Fresh red onions growing in soil farm field',
    'sibuyas': 'Fresh red onions growing in soil farm field',
    'garlic': 'Garlic plants growing in agricultural soil',
    'bawang': 'Garlic plants growing in agricultural soil',
    'cabbage': 'Fresh green cabbage heads growing in a farm',
    'repolyo': 'Fresh green cabbage heads growing in a farm',
    'potato': 'Potato plants growing in farm soil',
    'patatas': 'Potato plants growing in farm soil',
    'carrot': 'Fresh carrots growing in farm field soil',
    'karots': 'Fresh carrots growing in farm field soil',
    'coffee': 'Coffee cherries growing on coffee tree',
    'kape': 'Coffee cherries growing on coffee tree',
    'cacao': 'Cacao pods growing on cacao tree',
    'kakaw': 'Cacao pods growing on cacao tree',
    'pineapple': 'Pineapple growing on plant in plantation',
    'pinya': 'Pineapple growing on plant in plantation',
    'coconut': 'Coconut palms with coconuts in tropical plantation',
    'niyog': 'Coconut palms with coconuts in tropical plantation',
}

# Add a sensible search phrase for every catalog crop that does not already
# have a hand-written, crop-specific query.
for _entry in CROP_CATALOG:
    _generic_keyword = (
        f"{_entry['name']} crop plants growing in a farm field agricultural photograph"
    )
    CROP_KEYWORD_MAP.setdefault(_entry['name'].casefold(), _generic_keyword)
    for _alias in _entry['aliases']:
        CROP_KEYWORD_MAP.setdefault(_alias.casefold(), _generic_keyword)


def _build_verified_local_catalog():
    """Build the local photo catalog from verified catalog entries.

    A crop only appears here when the catalog points at a real local photo.
    Crops without a photo are deliberately omitted so the search picker never
    offers another crop's picture as a substitute.
    """

    catalog = {}
    for entry in CROP_CATALOG:
        image = entry.get('image')
        if not image:
            continue
        key = entry['name'].casefold()
        catalog[key] = [
            {
                'id': f"local-{key.replace(' ', '-')}-1",
                'title': entry['photo_title'],
                'thumb_url': f'/static/img/crops/{image}',
                'preview_url': f'/static/img/crops/{image}',
                'download_url': f'/static/img/crops/{image}',
                'source': 'Verified Agricultural Photo',
                'photographer': 'Wikimedia Commons',
                'photographer_url': 'https://commons.wikimedia.org',
                'alt': entry['photo_alt'],
                'verified': True,
            }
        ]
    return catalog


# Verified local agricultural photos with Wikimedia Commons attributions.
VERIFIED_LOCAL_CATALOG = _build_verified_local_catalog()


def get_search_keyword(crop_name):
    """Return an agricultural photograph search query for crop_name."""
    entry = find_catalog_entry(crop_name)
    if entry:
        key = entry['name'].casefold()
        return CROP_KEYWORD_MAP.get(
            key,
            f"{entry['name']} crop plants growing in a farm field agricultural photograph",
        )

    clean = (crop_name or '').strip().lower()
    for key, keyword in CROP_KEYWORD_MAP.items():
        if key == clean or key in clean:
            return keyword
    return f"{crop_name} crop plants growing in farm field agricultural photograph"


def search_unsplash(query, access_key, per_page=4):
    """Search Unsplash official API for realistic agricultural photographs."""
    if not access_key:
        return {'configured': False, 'photos': [], 'error': 'API key not configured'}

    url = 'https://api.unsplash.com/search/photos?' + urllib.parse.urlencode({
        'query': query,
        'per_page': per_page,
        'orientation': 'landscape',
        'content_filter': 'high',
    })

    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Client-ID {access_key}',
            'Accept-Version': 'v1',
            'User-Agent': 'HarvestPH/1.0',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            photos = []
            for item in data.get('results', []):
                urls = item.get('urls', {})
                user = item.get('user', {})
                photos.append({
                    'id': f"unsplash-{item.get('id')}",
                    'title': item.get('description') or item.get('alt_description') or 'Agricultural crop photo',
                    'thumb_url': urls.get('small') or urls.get('thumb'),
                    'preview_url': urls.get('regular') or urls.get('small'),
                    'download_url': urls.get('regular') or urls.get('full'),
                    'source': 'Unsplash',
                    'photographer': user.get('name', 'Unsplash Photographer'),
                    'photographer_url': user.get('links', {}).get('html', 'https://unsplash.com'),
                    'alt': item.get('alt_description') or 'Crop photograph from Unsplash',
                })
            return {'configured': True, 'photos': photos, 'error': None}
    except Exception as exc:
        logger.warning('Unsplash API search error: %s', exc)
        return {'configured': True, 'photos': [], 'error': str(exc)}


def search_pexels(query, api_key, per_page=4):
    """Search Pexels official API for realistic agricultural photographs."""
    if not api_key:
        return {'configured': False, 'photos': [], 'error': 'API key not configured'}

    url = 'https://api.pexels.com/v1/search?' + urllib.parse.urlencode({
        'query': query,
        'per_page': per_page,
        'orientation': 'landscape',
    })

    req = urllib.request.Request(
        url,
        headers={
            'Authorization': api_key,
            'User-Agent': 'HarvestPH/1.0',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            photos = []
            for item in data.get('photos', []):
                src = item.get('src', {})
                photos.append({
                    'id': f"pexels-{item.get('id')}",
                    'title': item.get('alt') or 'Agricultural crop photo',
                    'thumb_url': src.get('medium') or src.get('small'),
                    'preview_url': src.get('large') or src.get('medium'),
                    'download_url': src.get('large') or src.get('original'),
                    'source': 'Pexels',
                    'photographer': item.get('photographer', 'Pexels Photographer'),
                    'photographer_url': item.get('photographer_url', 'https://www.pexels.com'),
                    'alt': item.get('alt') or 'Crop photograph from Pexels',
                })
            return {'configured': True, 'photos': photos, 'error': None}
    except Exception as exc:
        logger.warning('Pexels API search error: %s', exc)
        return {'configured': True, 'photos': [], 'error': str(exc)}


def search_pixabay(query, api_key, per_page=4):
    """Search Pixabay official API for realistic agricultural photographs."""
    if not api_key:
        return {'configured': False, 'photos': [], 'error': 'API key not configured'}

    url = 'https://pixabay.com/api/?' + urllib.parse.urlencode({
        'key': api_key,
        'q': query,
        'image_type': 'photo',
        'per_page': per_page,
        'safesearch': 'true',
        'orientation': 'horizontal',
        'category': 'nature,industry',
    })

    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'HarvestPH/1.0'},
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            photos = []
            for item in data.get('hits', []):
                photos.append({
                    'id': f"pixabay-{item.get('id')}",
                    'title': item.get('tags') or 'Agricultural crop photo',
                    'thumb_url': item.get('webformatURL') or item.get('previewURL'),
                    'preview_url': item.get('largeImageURL') or item.get('webformatURL'),
                    'download_url': item.get('largeImageURL') or item.get('webformatURL'),
                    'source': 'Pixabay',
                    'photographer': item.get('user', 'Pixabay Photographer'),
                    'photographer_url': f"https://pixabay.com/users/{item.get('user')}-{item.get('user_id')}/",
                    'alt': item.get('tags') or 'Crop photograph from Pixabay',
                })
            return {'configured': True, 'photos': photos, 'error': None}
    except Exception as exc:
        logger.warning('Pixabay API search error: %s', exc)
        return {'configured': True, 'photos': [], 'error': str(exc)}


def get_verified_local_photos(crop_name):
    """Return matching verified agricultural photos from local catalog.

    Only photos for the requested crop are returned. Offering photos of other
    crops as a fallback can attach a completely wrong picture (for example a
    mango photo to a grape crop), so unknown crops get no catalog results and
    keep the neutral placeholder image instead.
    """
    entry = find_catalog_entry(crop_name)
    if not entry:
        return []
    return list(VERIFIED_LOCAL_CATALOG.get(entry['name'].casefold(), []))


def search_crop_images(crop_name):
    """Search for realistic crop photos across configured APIs and verified catalog."""
    keyword = get_search_keyword(crop_name)
    unsplash_key = getattr(settings, 'UNSPLASH_ACCESS_KEY', '') or os.environ.get('UNSPLASH_ACCESS_KEY', '')
    pexels_key = getattr(settings, 'PEXELS_API_KEY', '') or os.environ.get('PEXELS_API_KEY', '')
    pixabay_key = getattr(settings, 'PIXABAY_API_KEY', '') or os.environ.get('PIXABAY_API_KEY', '')

    unsplash_res = search_unsplash(keyword, unsplash_key)
    pexels_res = search_pexels(keyword, pexels_key)
    pixabay_res = search_pixabay(keyword, pixabay_key)

    api_photos = []
    api_photos.extend(unsplash_res['photos'])
    api_photos.extend(pexels_res['photos'])
    api_photos.extend(pixabay_res['photos'])

    local_photos = get_verified_local_photos(crop_name)

    # Verified local photos come first. They are the only photos the crop
    # form will auto-select, so the default photo always matches the crop.
    all_photos = local_photos + api_photos

    return {
        'keyword': keyword,
        'sources': {
            'unsplash': {
                'name': 'Unsplash',
                'configured': unsplash_res['configured'],
                'count': len(unsplash_res['photos']),
                'error': unsplash_res['error'],
            },
            'pexels': {
                'name': 'Pexels',
                'configured': pexels_res['configured'],
                'count': len(pexels_res['photos']),
                'error': pexels_res['error'],
            },
            'pixabay': {
                'name': 'Pixabay',
                'configured': pixabay_res['configured'],
                'count': len(pixabay_res['photos']),
                'error': pixabay_res['error'],
            },
        },
        'photos': all_photos,
    }


def save_image_from_url(image_url, crop_name='crop'):
    """Download an external or local image, verify it, and save locally into Django media.

    Returns the relative path stored in default_storage, suitable for crop.image.
    """
    if not image_url:
        return None

    # Handle local static paths (e.g. /static/img/crops/rice.jpg)
    if image_url.startswith('/static/'):
        clean_rel = image_url[len('/static/'):].split('?', 1)[0].split('#', 1)[0]
        local_static_path = Path(settings.BASE_DIR) / 'static' / clean_rel
        if local_static_path.is_file():
            with open(local_static_path, 'rb') as f:
                content = f.read()
            return _save_image_bytes(content, crop_name)

    # Handle remote HTTP/HTTPS image URLs
    if image_url.startswith('http://') or image_url.startswith('https://'):
        req = urllib.request.Request(
            image_url,
            headers={'User-Agent': 'HarvestPH/1.0 (Crop photo downloader)'},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
                return _save_image_bytes(content, crop_name)
        except Exception as exc:
            logger.error('Failed to download image from %s: %s', image_url, exc)
            return None

    return None


def _save_image_bytes(raw_bytes, crop_name):
    """Validate image bytes with PIL and save to MEDIA_ROOT/crops/%Y/%m/."""
    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            img.verify()
    except Exception as exc:
        logger.error('Invalid image content: %s', exc)
        return None

    now = timezone.now()
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', crop_name.lower())[:30]
    filename = f"crops/{now.strftime('%Y/%m')}/{clean_name}_{uuid.uuid4().hex[:8]}.jpg"

    saved_path = default_storage.save(filename, ContentFile(raw_bytes))
    return saved_path
