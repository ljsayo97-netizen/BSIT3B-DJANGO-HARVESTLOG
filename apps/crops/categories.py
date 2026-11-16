"""Crop categories and the keyword rules used to infer them."""

from .catalog import (
    CROP_CATALOG,
    FRUIT as CATEGORY_FRUIT,
    GRAIN as CATEGORY_GRAIN,
    OTHER as CATEGORY_OTHER,
    VEGETABLE as CATEGORY_VEGETABLE,
)

GRAIN_KEYWORDS = (
    "rice", "palay", "corn", "mais", "maize", "wheat", "sorghum", "barley",
    "millet", "oat", "adlay", "buckwheat", "quinoa",
)
VEGETABLE_KEYWORDS = (
    "tomato", "kamatis", "eggplant", "talong", "okra", "onion", "sibuyas",
    "garlic", "bawang", "cabbage", "repolyo", "carrot", "karots", "pechay",
    "pak choi", "pak choy", "bok choy", "lettuce", "letsugas", "cucumber",
    "pipino", "squash", "kalabasa", "pumpkin", "bitter gourd", "bitter melon",
    "bittermelon", "ampalaya", "mung bean", "mungbean", "munggo", "mongo",
    "soybean", "soya", "bean", "pepper", "chili", "sili", "spinach",
    "kangkong", "radish", "labanos", "beet", "broccoli", "cauliflower",
    "mustard", "mustasa", "ginger", "luya", "turmeric", "luyang dilaw",
    "potato", "patatas", "sweet potato", "kamote", "cassava", "kamoteng kahoy",
)
FRUIT_KEYWORDS = (
    "mango", "mangga", "banana", "saging", "lansones", "lanzones", "lanzon",
    "watermelon", "pakwan", "melon", "cantaloupe", "pineapple", "pinya",
    "coconut", "niyog", "papaya", "avocado", "durian", "rambutan", "grape",
    "orange", "calamansi", "lemon", "apple", "jackfruit", "langka",
)


def _catalog_keywords(category):
    """Return names and aliases for catalog crops in ``category``."""

    keywords = []
    for entry in CROP_CATALOG:
        if entry["category"] != category:
            continue
        for name in (entry["name"], *entry["aliases"]):
            lowered = name.casefold()
            if lowered not in keywords:
                keywords.append(lowered)
    return tuple(keywords)


def _merge_keywords(explicit, category):
    merged = list(explicit)
    for keyword in _catalog_keywords(category):
        if keyword not in merged:
            merged.append(keyword)
    return tuple(merged)


# Include every crop and alias from the comprehensive catalog so crops such as
# Dragon Fruit, Malunggay, or Adlay are classified automatically when added.
GRAIN_KEYWORDS = _merge_keywords(GRAIN_KEYWORDS, CATEGORY_GRAIN)
VEGETABLE_KEYWORDS = _merge_keywords(VEGETABLE_KEYWORDS, CATEGORY_VEGETABLE)
FRUIT_KEYWORDS = _merge_keywords(FRUIT_KEYWORDS, CATEGORY_FRUIT)

CATEGORY_RULES = (
    (CATEGORY_GRAIN, GRAIN_KEYWORDS),
    (CATEGORY_VEGETABLE, VEGETABLE_KEYWORDS),
    (CATEGORY_FRUIT, FRUIT_KEYWORDS),
)


def infer_category(crop_name):
    """Return the most likely category for ``crop_name``.

    The rules only use the crop's name, so they never overwrite a category
    the grower picked explicitly unless the name cannot be matched.
    """

    normalized = " ".join((crop_name or "").lower().split())
    if not normalized:
        return CATEGORY_OTHER

    for keyword in GRAIN_KEYWORDS:
        if keyword in normalized:
            return CATEGORY_GRAIN
    for keyword in VEGETABLE_KEYWORDS:
        if keyword in normalized:
            return CATEGORY_VEGETABLE
    for keyword in FRUIT_KEYWORDS:
        if keyword in normalized:
            return CATEGORY_FRUIT
    return CATEGORY_OTHER
