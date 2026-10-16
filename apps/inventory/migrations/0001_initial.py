# Creates the tblinventory and tblinventory_transactions tables.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('harvests', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_name', models.CharField(help_text='e.g. Rice, Corn, Mango', max_length=255, verbose_name='product name')),
                ('variety', models.CharField(blank=True, help_text='e.g. IR64, Hybrid, Carabao', max_length=255, verbose_name='variety')),
                ('quantity', models.DecimalField(decimal_places=2, help_text='Available stock quantity.', max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name='current quantity')),
                ('unit', models.CharField(choices=[('kg', 'Kilograms (kg)'), ('tons', 'Tons'), ('sacks', 'Sacks'), ('baskets', 'Baskets'), ('pieces', 'Pieces')], default='kg', max_length=20)),
                ('storage_location', models.CharField(help_text='e.g. Warehouse A, Cold Storage, Silo 1', max_length=255, verbose_name='storage location')),
                ('minimum_stock_level', models.DecimalField(decimal_places=2, default=0, help_text='Threshold below which stock is considered low.', max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name='minimum stock level')),
                ('status', models.CharField(choices=[('in_stock', 'In Stock'), ('low_stock', 'Low Stock'), ('out_of_stock', 'Out of Stock')], default='in_stock', max_length=20)),
                ('notes', models.TextField(blank=True, help_text='Observations about quality, expiry, etc.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source_harvest', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_items', to='harvests.harvest', verbose_name='source harvest')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='inventory_items', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblinventory',
                'ordering': ['-created_at'],
                'verbose_name': 'inventory item',
                'verbose_name_plural': 'inventory items',
            },
        ),
        migrations.CreateModel(
            name='InventoryTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('addition', 'Addition (Stock In)'), ('deduction', 'Deduction (Stock Out)'), ('adjustment', 'Adjustment')], max_length=20)),
                ('quantity', models.DecimalField(decimal_places=2, help_text='Quantity added or deducted.', max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('unit', models.CharField(max_length=20)),
                ('previous_quantity', models.DecimalField(decimal_places=2, max_digits=12)),
                ('new_quantity', models.DecimalField(decimal_places=2, max_digits=12)),
                ('reason', models.CharField(blank=True, help_text='e.g. New harvest delivery, Market sale, Spoilage', max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('transaction_date', models.DateTimeField(default=django.utils.timezone.now, verbose_name='transaction date')),
                ('performed_by', models.CharField(help_text='Person who recorded the transaction.', max_length=255, verbose_name='performed by')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('inventory_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='inventory.inventoryitem', verbose_name='inventory item')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='inventory_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'tblinventory_transactions',
                'ordering': ['-transaction_date', '-created_at'],
                'verbose_name': 'inventory transaction',
                'verbose_name_plural': 'inventory transactions',
            },
        ),
    ]
