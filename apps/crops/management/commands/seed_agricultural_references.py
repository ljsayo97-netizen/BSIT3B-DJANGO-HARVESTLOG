"""Seed verified Philippine agricultural reference data into the database."""

from django.core.management.base import BaseCommand

from apps.crops.agricultural_references_data import AGRICULTURAL_REFERENCES
from apps.crops.models import AgriculturalReference


def seed_references():
    """Ensure all official agricultural references are in the database.

    Also removes records that belong to reference sources that are no longer
    supported (for example the retired AMTEC and Anee sources), so the crop
    form only ever cites the current official Philippine references.
    """
    valid_sources = {choice for choice, _ in AgriculturalReference.Source.choices}

    removed_count, _ = AgriculturalReference.objects.exclude(
        source_name__in=valid_sources
    ).delete()

    created_count = 0
    updated_count = 0
    for data in AGRICULTURAL_REFERENCES:
        ref, created = AgriculturalReference.objects.update_or_create(
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
        if created:
            created_count += 1
        else:
            updated_count += 1
    return created_count, updated_count, removed_count


class Command(BaseCommand):
    help = (
        'Seeds verified Philippine agricultural reference data from Binhing '
        'Palay, PhilRice, ATI, and the Bureau of Plant Industry (BPI).'
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding agricultural reference data...'))
        created, updated, removed = seed_references()
        self.stdout.write(
            self.style.SUCCESS(
                'Agricultural references updated successfully: '
                f'{created} created, {updated} updated, {removed} removed.'
            )
        )
