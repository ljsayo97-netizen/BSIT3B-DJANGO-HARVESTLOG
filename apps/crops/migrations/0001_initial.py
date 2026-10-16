# Creates the tblcrops table for crop management.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('farms', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Crop',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, help_text='e.g. Rice, Corn, Mango', verbose_name='crop name')),
                ('variety', models.CharField(blank=True, help_text='e.g. IR64, Hybrid, Carabao', max_length=255, verbose_name='variety')),
                ('planting_date', models.DateField(default=django.utils.timezone.localdate, verbose_name='planting date')),
                ('expected_harvest_date', models.DateField(blank=True, null=True, verbose_name='expected harvest date')),
                ('actual_harvest_date', models.DateField(blank=True, null=True, verbose_name='actual harvest date')),
                ('status', models.CharField(choices=[('planting', 'Planting'), ('growing', 'Growing'), ('ready_for_harvest', 'Ready for Harvest'), ('harvested', 'Harvested'), ('failed', 'Failed')], default='planting', max_length=30)),
                ('area_hectares', models.DecimalField(decimal_places=2, help_text='Area planted in hectares.', max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='area (hectares)')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crops', to='farms.farm', verbose_name='farm')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='crops', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblcrops',
                'ordering': ['-planting_date', '-created_at'],
                'verbose_name': 'crop',
                'verbose_name_plural': 'crops',
            },
        ),
    ]
