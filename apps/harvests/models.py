"""Harvest readiness notifications and harvest records."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone


def _trim_number(value):
    """Render a number without trailing zeros (14.50 -> 14.5, 2500 stays 2500)."""
    return format(Decimal(str(value)).normalize(), 'f')


class HarvestNotification(models.Model):
    """An in-app alert created when a crop reaches harvest readiness."""

    class Kind(models.TextChoices):
        APPROACHING = 'approaching', 'Approaching harvest'
        READY = 'ready', 'Ready for harvest'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='harvest_notifications',
        on_delete=models.CASCADE,
    )
    crop = models.ForeignKey(
        'crops.Crop',
        related_name='harvest_notifications',
        on_delete=models.CASCADE,
        verbose_name='crop',
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.READY)
    expected_harvest_date = models.DateField(
        'expected harvest date',
        help_text='System-assigned harvest date this notification refers to.',
    )
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tblharvestnotifications'
        ordering = ['-created_at', '-id']
        verbose_name = 'harvest notification'
        verbose_name_plural = 'harvest notifications'
        unique_together = ('crop', 'kind', 'expected_harvest_date')

    def __str__(self):
        return f'{self.get_kind_display()} — {self.crop.name}'

    def mark_read(self):
        if self.is_read:
            return False
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])
        return True


class Harvest(models.Model):
    """A completed harvest record linked to a crop."""

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
    harvest_season = models.CharField('harvest season', max_length=100, blank=True, default='')
    harvest_date = models.DateField(
        'harvest date',
        default=timezone.localdate,
        help_text='Assigned automatically by the system when the harvest is recorded.',
    )
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

    def _generate_harvest_season(self):
        """Build the season label from the harvest date."""
        if self.harvest_season:
            return self.harvest_season
        ref_date = self.harvest_date or timezone.localdate()
        if ref_date.month in (12, 1, 2, 3, 4, 5):
            return f'Dry Season {ref_date.year}'
        return f'Wet Season {ref_date.year}'

    def save(self, *args, **kwargs):
        """Assign system defaults, a season, and a sequential harvest ID."""
        if not self.harvest_date:
            self.harvest_date = timezone.localdate()
        if not self.crop_type and self.crop_id:
            self.crop_type = self.crop.name
        if not self.location and self.farm_id:
            farm = self.farm
            self.location = farm.location or farm.name
        self.harvest_season = self._generate_harvest_season()

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
