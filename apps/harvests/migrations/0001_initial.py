# Creates the tblharvests table for harvest recording and history.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('farms', '0001_initial'),
        ('crops', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Harvest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('harvest_date', models.DateField(default=django.utils.timezone.localdate, verbose_name='harvest date')),
                ('location', models.CharField(help_text='Specific location within the farm (e.g. North field, Block A).', max_length=255, verbose_name='harvest location')),
                ('crop_type', models.CharField(help_text='Type of crop harvested (e.g. Rice, Corn, Mango).', max_length=255, verbose_name='crop type')),
                ('quantity_harvested', models.DecimalField(decimal_places=2, help_text='Amount harvested.', max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name='quantity harvested')),
                ('unit', models.CharField(default='kg', help_text='Unit of measure (e.g. kg, tons, baskets, sacks).', max_length=50, verbose_name='unit')),
                ('quality_grade', models.CharField(choices=[('premium', 'Premium'), ('grade_a', 'Grade A'), ('grade_b', 'Grade B'), ('grade_c', 'Grade C'), ('standard', 'Standard'), ('fair', 'Fair')], default='standard', max_length=30, verbose_name='quality / grade')),
                ('harvested_by', models.CharField(help_text='Person who performed the harvest.', max_length=255, verbose_name='harvested by')),
                ('supervised_by', models.CharField(blank=True, help_text='Person who supervised the harvest (optional).', max_length=255, verbose_name='supervised by')),
                ('notes', models.TextField(blank=True, help_text='Observations and notes.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('crop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='harvests', to='crops.crop', verbose_name='crop')),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='harvests', to='farms.farm', verbose_name='farm')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='harvests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblharvests',
                'ordering': ['-harvest_date', '-created_at'],
                'verbose_name': 'harvest',
                'verbose_name_plural': 'harvests',
            },
        ),
    ]
