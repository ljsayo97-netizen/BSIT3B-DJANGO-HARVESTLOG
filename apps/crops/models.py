"""Crop management models."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Crop(models.Model):
    """A crop planted on a farm."""

    class Status(models.TextChoices):
        PLANTING = 'planting', 'Planting'
        GROWING = 'growing', 'Growing'
        READY_FOR_HARVEST = 'ready_for_harvest', 'Ready for Harvest'
        HARVESTED = 'harvested', 'Harvested'
        FAILED = 'failed', 'Failed'

    farm = models.ForeignKey(
        'farms.Farm',
        related_name='crops',
        on_delete=models.CASCADE,
        verbose_name='farm',
    )
    name = models.CharField('crop name', max_length=255, help_text='e.g. Rice, Corn, Mango')
    variety = models.CharField('variety', max_length=255, blank=True, help_text='e.g. IR64, Hybrid, Carabao')
    planting_date = models.DateField('planting date', default=timezone.localdate)
    expected_harvest_date = models.DateField('expected harvest date', blank=True, null=True)
    actual_harvest_date = models.DateField('actual harvest date', blank=True, null=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PLANTING,
    )
    area_hectares = models.DecimalField(
        'area (hectares)',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Area planted in hectares.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='crops',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblcrops'
        ordering = ['-planting_date', '-created_at']
        verbose_name = 'crop'
        verbose_name_plural = 'crops'

    def __str__(self):
        return f'{self.name} ({self.variety or "n/a"}) on {self.farm.name}'

    @property
    def days_since_planting(self):
        if self.planting_date:
            return (timezone.localdate() - self.planting_date).days
        return None

    @property
    def days_to_harvest(self):
        if self.expected_harvest_date:
            return (self.expected_harvest_date - timezone.localdate()).days
        return None
