"""Agricultural Variety and Harvest Date Generation Service.

Integrates Philippine agricultural references:
- Binhing Palay (https://binhingpalay.philrice.gov.ph/)
- PhilRice (https://www.philrice.gov.ph/)
- Agricultural Training Institute (ATI) (https://ati.da.gov.ph/)
- Bureau of Plant Industry (BPI) (https://library.buplant.da.gov.ph/)
"""

from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from .maturity import suggest_maturity_days, CROP_MATURITY_DAYS, DEFAULT_MATURITY_DAYS
from .models import AgriculturalReference


HARVEST_DATE_DISCLAIMER = (
    "Expected harvest dates are estimates based on published crop maturity information. "
    "Actual harvesting schedules may vary depending on environmental conditions and farming practices."
)

CROP_NAME_SYNONYMS = {
    'palay': 'Rice',
    'mais': 'Corn',
    'kamatis': 'Tomato',
    'talong': 'Eggplant',
    'ampalaya': 'Ampalaya',
    'bitter gourd': 'Ampalaya',
    'bitter melon': 'Ampalaya',
    'pechay': 'Pechay',
    'pak choi': 'Pechay',
    'bok choy': 'Pechay',
    'okra': 'Okra',
    'sitaw': 'Pole Sitao',
    'pole sitao': 'Pole Sitao',
    'kalabasa': 'Squash',
    'squash': 'Squash',
    'sibuyas': 'Onion',
    'onion': 'Onion',
    'bawang': 'Garlic',
    'garlic': 'Garlic',
    'sili': 'Hot Pepper',
    'pepper': 'Hot Pepper',
    'repolyo': 'Cabbage',
    'cabbage': 'Cabbage',
    'tubo': 'Sugarcane',
    'sugar cane': 'Sugarcane',
    'sugarcane': 'Sugarcane',
    'kamoteng kahoy': 'Cassava',
    'cassava': 'Cassava',
    'kamote': 'Sweet Potato',
    'sweet potato': 'Sweet Potato',
    'mani': 'Peanut',
    'peanut': 'Peanut',
    'pakwan': 'Watermelon',
    'watermelon': 'Watermelon',
    'melon': 'Melon',
    'pipino': 'Cucumber',
    'cucumber': 'Cucumber',
    'letsugas': 'Lettuce',
    'lettuce': 'Lettuce',
    'saging': 'Banana',
    'banana': 'Banana',
    'mangga': 'Mango',
    'mango': 'Mango',
}


def normalize_crop_name(name):
    """Map local synonyms or common names to canonical crop name."""
    clean = (name or '').strip().lower()
    for syn, canonical in CROP_NAME_SYNONYMS.items():
        if syn == clean or syn in clean:
            return canonical
    return (name or '').strip().title()


def search_varieties(crop_name, category=None):
    """Retrieve verified crop varieties from agricultural references."""
    if not crop_name:
        return []

    canonical = normalize_crop_name(crop_name)
    raw_query = crop_name.strip()

    qs = AgriculturalReference.objects.filter(is_active=True)

    # Filter matching crop name or variety name
    matches = qs.filter(
        Q(crop_name__iexact=canonical) |
        Q(crop_name__icontains=raw_query) |
        Q(variety_name__icontains=raw_query)
    )

    if not matches.exists() and category:
        matches = qs.filter(category=category)

    results = []
    for item in matches.order_by('variety_name'):
        results.append({
            'id': item.id,
            'crop_name': item.crop_name,
            'variety_name': item.variety_name,
            'category': item.category,
            'category_display': item.get_category_display(),
            'days_to_maturity': item.days_to_maturity,
            'days_to_maturity_min': item.days_to_maturity_min,
            'days_to_maturity_max': item.days_to_maturity_max,
            'source_name': item.source_name,
            'source_url': item.source_url,
            'description': item.description,
            'soil_type': item.soil_type,
            'irrigation_info': item.irrigation_info,
            'verified_date': item.verified_date.isoformat() if item.verified_date else None,
        })
    return results


def calculate_harvest_date(planting_date, days_to_maturity):
    """Formula: Expected Harvest Date = Planting Date + Days to Maturity."""
    if not planting_date or not days_to_maturity or days_to_maturity < 1:
        return None
    return planting_date + timedelta(days=int(days_to_maturity))
