"""Harvest recording and history models."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Harvest(models.Model):
    """A harvest record linked to a farm and optionally a crop."""

    class QualityGrade(models.TextChoices):
        PREMIUM = 'premium', 'Premium'
        GRADE_A = 'grade_a', 'Grade A'
        GRADE_B = 'grade_b', 'Grade B'
        GRADE_C = 'grade_c', 'Grade C'
        STANDARD = 'standard', 'Standard'
        FAIR = 'fair', 'Fair'

    farm = models.ForeignKey(
        'farms.Farm',
        related_name='harvests',
        on_delete=models.CASCADE,
        verbose_name='farm',
    )
    crop = models.ForeignKey(
        'crops.Crop',
        related_name='harvests',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='crop',
    )
    harvest_date = models.DateField('harvest date', default=timezone.localdate)
    location = models.CharField(
        'harvest location',
        max_length=255,
        help_text='Specific location within the farm (e.g. North field, Block A).',
    )
    crop_type = models.CharField(
        'crop type',
        max_length=255,
        help_text='Type of crop harvested (e.g. Rice, Corn, Mango).',
    )
    quantity_harvested = models.DecimalField(
        'quantity harvested',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Amount harvested.',
    )
    unit = models.CharField(
        'unit',
        max_length=50,
        default='kg',
        help_text='Unit of measure (e.g. kg, tons, baskets, sacks).',
    )
    quality_grade = models.CharField(
        'quality / grade',
        max_length=30,
        choices=QualityGrade.choices,
        default=QualityGrade.STANDARD,
    )
    harvested_by = models.CharField(
        'harvested by',
        max_length=255,
        help_text='Person who performed the harvest.',
    )
    supervised_by = models.CharField(
        'supervised by',
        max_length=255,
        blank=True,
        help_text='Person who supervised the harvest (optional).',
    )
    notes = models.TextField(blank=True, help_text='Observations and notes.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='harvests',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblharvests'
        ordering = ['-harvest_date', '-created_at']
        verbose_name = 'harvest'
        verbose_name_plural = 'harvests'

    def __str__(self):
        return f'{self.crop_type} harvest on {self.harvest_date} ({self.farm.name})'
