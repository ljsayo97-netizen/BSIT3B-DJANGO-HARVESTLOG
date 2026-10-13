from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Crop(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='crops',
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    variety = models.CharField(max_length=120, blank=True)
    farm_name = models.CharField(max_length=150)
    farm_location = models.CharField(max_length=255, blank=True)
    farm_size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    farm_size_unit = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'variety', 'farm_name']
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'name', 'variety', 'farm_name'],
                name='unique_crop_variety_farm_per_owner',
            ),
        ]

    def __str__(self):
        variety = f' ({self.variety})' if self.variety else ''
        return f'{self.name}{variety} — {self.farm_name}'


class Harvest(models.Model):
    class Unit(models.TextChoices):
        KILOGRAM = 'kg', 'Kilograms (kg)'
        GRAM = 'g', 'Grams (g)'
        TONNE = 'tonne', 'Tonnes'
        POUND = 'lb', 'Pounds (lb)'
        BUSHEL = 'bushel', 'Bushels'
        CRATE = 'crate', 'Crates'
        PIECE = 'piece', 'Pieces'

    crop = models.ForeignKey(Crop, related_name='harvests', on_delete=models.CASCADE)
    harvest_date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    unit = models.CharField(max_length=10, choices=Unit.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-harvest_date', '-created_at']

    def __str__(self):
        return f'{self.crop}: {self.quantity} {self.unit} on {self.harvest_date}'

    @property
    def quantity_sold(self):
        return self.sales.aggregate(total=Sum('quantity'))['total'] or Decimal('0')

    @property
    def quantity_remaining(self):
        return self.quantity - self.quantity_sold


class Sale(models.Model):
    harvest = models.ForeignKey(Harvest, related_name='sales', on_delete=models.CASCADE)
    sold_on = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    buyer = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sold_on', '-created_at']

    def __str__(self):
        return f'{self.quantity} {self.harvest.unit} of {self.harvest.crop.name}'

    @property
    def total_revenue(self):
        return self.quantity * self.unit_price
