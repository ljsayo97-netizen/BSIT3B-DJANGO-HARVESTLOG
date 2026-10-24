"""Crop management models."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


HARVEST_APPROACHING_DAYS = 14
HARVEST_UPCOMING_WINDOW_DAYS = 30


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
    name = models.CharField('crop name', max_length=255)
    variety = models.CharField('variety', max_length=255, blank=True)
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

    @property
    def maturity_status(self):
        """Return the crop's harvest-readiness stage."""
        if self.actual_harvest_date or self.status == self.Status.HARVESTED:
            return 'harvested'
        if self.status == self.Status.FAILED:
            return 'failed'

        days = self.days_to_harvest
        if self.status == self.Status.READY_FOR_HARVEST or (days is not None and days <= 0):
            return 'ready'
        if days is not None and days <= HARVEST_APPROACHING_DAYS:
            return 'approaching'
        return 'upcoming'

    @property
    def maturity_label(self):
        labels = {
            'ready': 'Ready for harvest',
            'approaching': 'Approaching harvest',
            'upcoming': 'Upcoming harvest',
            'harvested': 'Harvested',
            'failed': 'Failed',
        }
        return labels.get(self.maturity_status, 'Upcoming harvest')

    @property
    def days_to_harvest_label(self):
        days = self.days_to_harvest
        if days is None:
            return 'Ready now' if self.maturity_status == 'ready' else '—'
        if days == 0:
            return 'Today'
        if days == 1:
            return 'Tomorrow'
        if days > 0:
            return f'In {days} days'
        return f'{abs(days)} day{"s" if abs(days) != 1 else ""} overdue'
