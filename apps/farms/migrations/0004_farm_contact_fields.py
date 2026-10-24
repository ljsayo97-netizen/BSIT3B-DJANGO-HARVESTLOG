# Auto-generated farm IDs plus owner contact details for farms.

from django.db import migrations, models


def assign_farm_codes(apps, schema_editor):
    """Give every existing farm its auto-generated ID, e.g. FARM-0001."""
    Farm = apps.get_model('farms', 'Farm')
    for farm in Farm.objects.filter(farm_code='').order_by('pk'):
        Farm.objects.filter(pk=farm.pk).update(farm_code=f'FARM-{farm.pk:04d}')


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0003_alter_farm_options_alter_farm_managers'),
    ]

    operations = [
        migrations.AddField(
            model_name='farm',
            name='email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='email'),
        ),
        migrations.AddField(
            model_name='farm',
            name='contact_number',
            field=models.CharField(
                blank=True,
                help_text='Contact number of the farm owner or manager.',
                max_length=50,
                verbose_name='contact number',
            ),
        ),
        migrations.AddField(
            model_name='farm',
            name='zip_code',
            field=models.CharField(blank=True, max_length=20, verbose_name='ZIP code'),
        ),
        # Added without the unique constraint first so existing rows can be
        # backfilled below; MySQL rejects a unique column full of duplicates.
        migrations.AddField(
            model_name='farm',
            name='farm_code',
            field=models.CharField(
                blank=True,
                editable=False,
                help_text='Auto-generated farm ID, for example FARM-0001.',
                max_length=20,
                verbose_name='farm ID',
            ),
        ),
        migrations.RunPython(assign_farm_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='farm',
            name='farm_code',
            field=models.CharField(
                blank=True,
                editable=False,
                help_text='Auto-generated farm ID, for example FARM-0001.',
                max_length=20,
                unique=True,
                verbose_name='farm ID',
            ),
        ),
    ]
