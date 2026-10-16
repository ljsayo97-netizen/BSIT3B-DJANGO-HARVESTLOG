"""Inventory management models for tracking harvested products."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class InventoryItem(models.Model):
    """Current stock record for a harvested product."""

    class Status(models.TextChoices):
        IN_STOCK = 'in_stock', 'In Stock'
        LOW_STOCK = 'low_stock', 'Low Stock'
        OUT_OF_STOCK = 'out_of_stock', 'Out of Stock'

    class Unit(models.TextChoices):
        KG = 'kg', 'Kilograms (kg)'
        TONS = 'tons', 'Tons'
        SACKS = 'sacks', 'Sacks'
        BASKETS = 'baskets', 'Baskets'
        PIECES = 'pieces', 'Pieces'

    product_name = models.CharField('product name', max_length=255, help_text='e.g. Rice, Corn, Mango')
    variety = models.CharField('variety', max_length=255, blank=True, help_text='e.g. IR64, Hybrid, Carabao')
    quantity = models.DecimalField(
        'current quantity',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Available stock quantity.',
    )
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.KG)
    storage_location = models.CharField(
        'storage location',
        max_length=255,
        help_text='e.g. Warehouse A, Cold Storage, Silo 1',
    )
    minimum_stock_level = models.DecimalField(
        'minimum stock level',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
        help_text='Threshold below which stock is considered low.',
    )
    source_harvest = models.ForeignKey(
        'harvests.Harvest',
        related_name='inventory_items',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='source harvest',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_STOCK)
    notes = models.TextField(blank=True, help_text='Observations about quality, expiry, etc.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='inventory_items',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblinventory'
        ordering = ['-created_at']
        verbose_name = 'inventory item'
        verbose_name_plural = 'inventory items'

    def __str__(self):
        return f'{self.product_name} ({self.quantity} {self.unit})'

    @property
    def is_low_stock(self):
        return self.quantity <= self.minimum_stock_level and self.quantity > 0

    @property
    def is_out_of_stock(self):
        return self.quantity <= 0


class InventoryTransaction(models.Model):
    """Record of each stock addition or deduction."""

    class TransactionType(models.TextChoices):
        ADDITION = 'addition', 'Addition (Stock In)'
        DEDUCTION = 'deduction', 'Deduction (Stock Out)'
        ADJUSTMENT = 'adjustment', 'Adjustment'

    inventory_item = models.ForeignKey(
        InventoryItem,
        related_name='transactions',
        on_delete=models.CASCADE,
        verbose_name='inventory item',
    )
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Quantity added or deducted.',
    )
    unit = models.CharField(max_length=20)
    previous_quantity = models.DecimalField(max_digits=12, decimal_places=2)
    new_quantity = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True, help_text='e.g. New harvest delivery, Market sale, Spoilage')
    notes = models.TextField(blank=True)
    transaction_date = models.DateTimeField('transaction date', default=timezone.now)
    performed_by = models.CharField('performed by', max_length=255, help_text='Person who recorded the transaction.')
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='inventory_transactions',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblinventory_transactions'
        ordering = ['-transaction_date', '-created_at']
        verbose_name = 'inventory transaction'
        verbose_name_plural = 'inventory transactions'

    def __str__(self):
        return f'{self.get_transaction_type_display()} - {self.quantity} {self.unit}'
