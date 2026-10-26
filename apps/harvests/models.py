"""Harvest scheduling and recording models."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone


def _trim_number(value):
    """Render a number without trailing zeros (14.50 -> 14.5, 2500 stays 2500)."""
    return format(Decimal(str(value)).normalize(), 'f')


class HarvestSchedule(models.Model):
    """A planned harvesting activity with workers assigned to it."""

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    STATUS_ACTIVE = (Status.SCHEDULED, Status.IN_PROGRESS)

    farm = models.ForeignKey(
        'farms.Farm',
        related_name='harvest_schedules',
        on_delete=models.CASCADE,
        verbose_name='farm',
    )
    crop = models.ForeignKey(
        'crops.Crop',
        related_name='harvest_schedules',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='crop',
    )
    field_name = models.CharField(
        'location',
        max_length=255,
        help_text='Location where the harvest will take place (e.g. North Field, Block A).',
    )
    scheduled_date = models.DateField('scheduled date', default=timezone.localdate)
    expected_quantity = models.DecimalField(
        'expected quantity',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Estimated amount to be harvested.',
    )
    unit = models.CharField(
        'unit',
        max_length=50,
        default='kg',
        help_text='Unit of measure (e.g. kg, tons, baskets, sacks).',
    )
    workers_count = models.PositiveIntegerField(
        'workers',
        default=1,
        validators=[MinValueValidator(1)],
        help_text='Number of workers assigned to the harvest.',
    )
    assigned_to = models.CharField(
        'assigned workers / team',
        max_length=255,
        blank=True,
        help_text='Names of workers or the team assigned to the activity.',
    )
    supervisor = models.CharField(
        'supervised by',
        max_length=255,
        blank=True,
        help_text='Person who will supervise the harvest (optional).',
    )
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    notes = models.TextField(
        'scheduling notes',
        blank=True,
        help_text='Instructions, reminders, or other notes for the harvest team.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='harvest_schedules',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblharvestschedules'
        ordering = ['scheduled_date', 'id']
        verbose_name = 'harvest schedule'
        verbose_name_plural = 'harvest schedules'

    def __str__(self):
        crop_name = self.crop.name if self.crop else 'Harvest'
        return f'{crop_name} on {self.field_name} ({self.scheduled_date})'

    @property
    def is_active(self):
        return self.status in self.STATUS_ACTIVE

    @property
    def days_until(self):
        if self.scheduled_date:
            return (self.scheduled_date - timezone.localdate()).days
        return None


class Harvest(models.Model):
    """A harvest record linked to a farm and optionally a crop."""

    class QualityGrade(models.TextChoices):
        PREMIUM = 'premium', 'Premium'
        GRADE_A = 'grade_a', 'Grade A'
        GRADE_B = 'grade_b', 'Grade B'
        GRADE_C = 'grade_c', 'Grade C'
        STANDARD = 'standard', 'Standard'
        FAIR = 'fair', 'Fair'

    class Condition(models.TextChoices):
        FRESH = 'fresh', 'Fresh'
        DRY = 'dry', 'Dry'
        WET = 'wet', 'Wet'
        DISCOLORED = 'discolored', 'Discolored'
        MOLDY = 'moldy', 'Moldy'
        PEST_AFFECTED = 'pest_affected', 'Pest-affected'
        MIXED = 'mixed', 'Mixed'

    harvest_code = models.CharField(
        'harvest ID',
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text='Automatically generated harvest reference (e.g. HL-2026-001).',
    )
    schedule = models.OneToOneField(
        HarvestSchedule,
        related_name='harvest_record',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='harvest schedule',
    )
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
        'field / location',
        max_length=255,
        help_text='Field or location within the farm (e.g. Field A, North field, Block A).',
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
    quality_condition = models.CharField(
        'condition',
        max_length=30,
        choices=Condition.choices,
        blank=True,
        help_text='Condition of the harvested produce, documented after the harvest.',
    )
    moisture_level = models.DecimalField(
        'moisture level (%)',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Moisture content of the produce, in percent.',
    )
    damaged_quantity = models.DecimalField(
        'damaged quantity',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Amount lost or damaged, in the harvest unit.',
    )
    quality_observations = models.TextField(
        'quality observations',
        blank=True,
        help_text='General observations about the harvested produce.',
    )
    quality_recorded_at = models.DateTimeField(
        'quality recorded at',
        null=True,
        blank=True,
        help_text='When the quality & observation record was documented.',
    )
    workers_count = models.PositiveIntegerField(
        'workers',
        default=0,
        help_text='Number of workers who took part in the harvest.',
    )
    harvested_by = models.CharField(
        'harvest team lead',
        max_length=255,
        help_text='Person who led or performed the harvest.',
    )
    supervised_by = models.CharField(
        'supervised by',
        max_length=255,
        blank=True,
        help_text='Person who supervised the harvest (optional).',
    )
    notes = models.TextField('remarks', blank=True, help_text='Observations and remarks.')
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
        reference = self.harvest_code or 'Harvest'
        fruit = self.crop_type or (self.crop.name if self.crop else 'Crop')
        return f'{reference} — {fruit} ({self.farm.name})'

    @property
    def has_quality_record(self):
        """Whether quality & observations have been documented."""
        return (
            self.quality_recorded_at is not None
            or bool(self.quality_condition)
            or self.moisture_level is not None
            or self.damaged_quantity is not None
            or bool(self.quality_observations)
        )

    @property
    def quality_details(self):
        """Short quality details for compact display in the history table."""
        details = []
        if self.quality_condition:
            details.append(self.get_quality_condition_display())
        if self.moisture_level is not None:
            details.append(f'{_trim_number(self.moisture_level)}% moisture')
        if self.damaged_quantity is not None:
            details.append(f'{_trim_number(self.damaged_quantity)} {self.unit} damaged')
        return details

    def _next_harvest_code(self):
        """Build the next sequential code for the harvest year."""
        year = (self.harvest_date or timezone.localdate()).year
        prefix = f'HL-{year}-'
        codes = Harvest.objects.filter(
            harvest_code__startswith=prefix,
        ).values_list('harvest_code', flat=True)

        highest = 0
        for code in codes:
            try:
                highest = max(highest, int(code.rsplit('-', 1)[1]))
            except (AttributeError, IndexError, ValueError):
                continue
        return f'{prefix}{highest + 1:03d}'

    def save(self, *args, **kwargs):
        """Assign a sequential harvest ID the first time a record is saved."""
        if self.harvest_code:
            return super().save(*args, **kwargs)

        for attempt in range(5):
            self.harvest_code = self._next_harvest_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.harvest_code = None
                if attempt == 4:
                    raise
