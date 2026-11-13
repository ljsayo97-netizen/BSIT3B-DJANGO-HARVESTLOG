"""Backfill crop categories for records that existed before the inventory UI."""

from django.db import migrations


GRAIN_KEYWORDS = (
    'rice', 'palay', 'corn', 'mais', 'maize', 'wheat', 'sorghum', 'barley',
    'millet', 'oat',
)
VEGETABLE_KEYWORDS = (
    'tomato', 'kamatis', 'eggplant', 'talong', 'okra', 'onion', 'sibuyas',
    'garlic', 'bawang', 'cabbage', 'repolyo', 'carrot', 'karots', 'pechay',
    'pak choi', 'pak choy', 'bok choy', 'lettuce', 'letsugas', 'cucumber',
    'pipino', 'squash', 'kalabasa', 'pumpkin', 'bitter gourd', 'bitter melon',
    'bittermelon', 'ampalaya', 'mung bean', 'mungbean', 'munggo', 'mongo',
    'soybean', 'soya', 'bean', 'pepper', 'chili', 'sili', 'spinach',
    'kangkong', 'radish', 'labanos', 'beet', 'broccoli', 'cauliflower',
    'mustard', 'mustasa', 'ginger', 'luya', 'turmeric', 'luyang dilaw',
    'potato', 'patatas', 'sweet potato', 'kamote', 'cassava', 'kamoteng kahoy',
)
FRUIT_KEYWORDS = (
    'mango', 'mangga', 'banana', 'saging', 'lansones', 'lanzones', 'lanzon',
    'watermelon', 'pakwan', 'melon', 'cantaloupe', 'pineapple', 'pinya',
    'coconut', 'niyog', 'papaya', 'avocado', 'durian', 'rambutan', 'grape',
    'orange', 'calamansi', 'lemon', 'apple', 'jackfruit', 'langka',
)


def infer_category(crop_name):
    normalized = ' '.join((crop_name or '').lower().split())
    if not normalized:
        return 'other'
    for keyword in GRAIN_KEYWORDS:
        if keyword in normalized:
            return 'grain'
    for keyword in VEGETABLE_KEYWORDS:
        if keyword in normalized:
            return 'vegetable'
    for keyword in FRUIT_KEYWORDS:
        if keyword in normalized:
            return 'fruit'
    return 'other'


def backfill_categories(apps, schema_editor):
    Crop = apps.get_model('crops', 'Crop')
    for crop in Crop.objects.all().iterator():
        category = infer_category(crop.name)
        if crop.category != category:
            crop.category = category
            crop.save(update_fields=['category'])


class Migration(migrations.Migration):

    dependencies = [
        ('crops', '0009_crop_category_crop_estimated_yield_crop_image'),
    ]

    operations = [
        migrations.RunPython(backfill_categories, migrations.RunPython.noop),
    ]
