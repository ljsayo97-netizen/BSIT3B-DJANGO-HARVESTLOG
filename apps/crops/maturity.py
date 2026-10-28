"""Reference data used to estimate how long a crop takes to mature."""

DEFAULT_MATURITY_DAYS = 90

# Typical days from planting to harvest for common Philippine crops.
# The values are estimates only; growers can override them per crop.
CROP_MATURITY_DAYS = {
    'rice': 110,
    'palay': 110,
    'corn': 100,
    'mais': 100,
    'sugarcane': 330,
    'tubo': 330,
    'tomato': 70,
    'kamatis': 70,
    'eggplant': 80,
    'talong': 80,
    'okra': 60,
    'onion': 120,
    'sibuyas': 120,
    'garlic': 120,
    'bawang': 120,
    'cabbage': 75,
    'repolyo': 75,
    'carrot': 90,
    'karots': 90,
    'potato': 100,
    'patatas': 100,
    'cassava': 300,
    'kamoteng kahoy': 300,
    'sweet potato': 120,
    'kamote': 120,
    'peanut': 120,
    'mani': 120,
    'mung bean': 65,
    'munggo': 65,
    'soybean': 100,
    'banana': 270,
    'saging': 270,
    'mango': 120,
    'mangga': 120,
    'coconut': 365,
    'niyog': 365,
    'coffee': 240,
    'kape': 240,
    'cacao': 180,
    'pineapple': 540,
    'pinya': 540,
    'watermelon': 80,
    'pakwan': 80,
    'melon': 80,
    'cucumber': 55,
    'pipino': 55,
    'squash': 90,
    'kalabasa': 90,
    'ampalaya': 70,
    'bitter gourd': 70,
    'pechay': 30,
    'lettuce': 45,
    'ginger': 240,
    'luya': 240,
    'turmeric': 270,
    'luyang dilaw': 270,
    'tobacco': 120,
    'tabako': 120,
}


def suggest_maturity_days(crop_name):
    """Return an estimated days-to-maturity value for a crop name."""
    normalized = ' '.join((crop_name or '').lower().split())
    if not normalized:
        return DEFAULT_MATURITY_DAYS

    if normalized in CROP_MATURITY_DAYS:
        return CROP_MATURITY_DAYS[normalized]

    # Match names such as "Rice (IR64)" or "Sweet corn".
    for keyword, days in CROP_MATURITY_DAYS.items():
        if keyword in normalized:
            return days
    return DEFAULT_MATURITY_DAYS
