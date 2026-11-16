from django.db import migrations


def seed_references_forward(apps, schema_editor):
    from apps.crops.agricultural_references_data import AGRICULTURAL_REFERENCES
    AgriculturalReference = apps.get_model('crops', 'AgriculturalReference')

    for data in AGRICULTURAL_REFERENCES:
        AgriculturalReference.objects.update_or_create(
            crop_name=data['crop_name'],
            variety_name=data['variety_name'],
            source_name=data['source_name'],
            defaults={
                'category': data['category'],
                'days_to_maturity': data['days_to_maturity'],
                'days_to_maturity_min': data.get('days_to_maturity_min'),
                'days_to_maturity_max': data.get('days_to_maturity_max'),
                'source_url': data['source_url'],
                'description': data.get('description', ''),
                'soil_type': data.get('soil_type', ''),
                'irrigation_info': data.get('irrigation_info', ''),
                'verified_date': data.get('verified_date'),
                'is_active': True,
            },
        )


def seed_references_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('crops', '0011_agriculturalreference_crop_reference_source_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_references_forward, seed_references_backward),
    ]
