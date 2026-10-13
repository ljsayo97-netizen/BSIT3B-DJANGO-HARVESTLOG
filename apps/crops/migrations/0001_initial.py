import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Crop',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('variety', models.CharField(blank=True, max_length=120)),
                ('farm_name', models.CharField(max_length=150)),
                ('farm_location', models.CharField(blank=True, max_length=255)),
                ('farm_size', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('farm_size_unit', models.CharField(blank=True, max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crops', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name', 'variety', 'farm_name'],
            },
        ),
        migrations.CreateModel(
            name='Harvest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('harvest_date', models.DateField(default=django.utils.timezone.localdate)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.001'))])),
                ('unit', models.CharField(choices=[('kg', 'Kilograms (kg)'), ('g', 'Grams (g)'), ('tonne', 'Tonnes'), ('lb', 'Pounds (lb)'), ('bushel', 'Bushels'), ('crate', 'Crates'), ('piece', 'Pieces')], max_length=10)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('crop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='harvests', to='crops.crop')),
            ],
            options={
                'ordering': ['-harvest_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Sale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sold_on', models.DateField(default=django.utils.timezone.localdate)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.001'))])),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('buyer', models.CharField(blank=True, max_length=150)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('harvest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales', to='crops.harvest')),
            ],
            options={
                'ordering': ['-sold_on', '-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='crop',
            constraint=models.UniqueConstraint(fields=('owner', 'name', 'variety', 'farm_name'), name='unique_crop_variety_farm_per_owner'),
        ),
    ]
