# Creates the tblfarms table for farm registration and management.

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Farm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='farm name')),
                ('owner', models.CharField(max_length=255, verbose_name='owner / manager')),
                ('location', models.CharField(max_length=255)),
                ('size_hectares', models.DecimalField(decimal_places=2, help_text='Farm size in hectares.', max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='size (hectares)')),
                ('description', models.TextField(blank=True)),
                ('date_registered', models.DateTimeField(verbose_name='date registered')),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('archived', 'Archived')], default='active', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='farms', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblfarms',
                'ordering': ['-date_registered'],
                'verbose_name': 'farm',
                'verbose_name_plural': 'farms',
            },
        ),
    ]
