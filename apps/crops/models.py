"""Crop management models."""

from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.utils import timezone

from .images import crop_image_path
from .maturity import DEFAULT_MATURITY_DAYS, suggest_maturity_days


class CropDefaultImage(models.Model):
    """Tracks a user's default uploaded image per crop name, surviving
    deletion/reenactment of individual crop instances.

    When a crop image is uploaded via the form, this record is created/updated
    so that ``display_image_url`` can return it even after the crop instance's
    ``image`` field is cleared.
    """

    class Meta:
        verbose_name = "crop default image"
        verbose_name_plural = "crop default images"
        unique_together = ("user", "crop_name")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crop_default_images",
    )
    crop_name = models.CharField("crop name", max_length=255)
    image_path = models.CharField("image path", max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} / {self.crop_name} / {self.image_path}"


HARVEST_APPROACHING_DAYS = 14
HARVEST_UPCOMING_WINDOW_DAYS = 30


class Crop(models.Model):
    """A crop planted on a farm."""

    class Status(models.TextChoices):
        PLANTING = 'planting', 'Planted'
        GROWING = 'growing', '🌿 Growing'
        MATURING = 'maturing', '🌾 Maturing'
        READY_FOR_HARVEST = 'ready_for_harvest', '🟡 Ready for Harvest'
        HARVESTED = 'harvested', '✅ Harvested'
        FAILED = 'failed', '⚠️ Damaged/Failed'

    class Quality(models.TextChoices):
        """Quality grades, mirroring the harvest quality scale."""
        PREMIUM = 'premium', 'Premium'
        GRADE_A = 'grade_a', 'Grade A'
        GRADE_B = 'grade_b', 'Grade B'
        GRADE_C = 'grade_c', 'Grade C'
        STANDARD = 'standard', 'Standard'
        FAIR = 'fair', 'Fair'

    class Category(models.TextChoices):
        """Broad crop groups used by the crop inventory filters."""
        VEGETABLE = 'vegetable', 'Vegetables'
        GRAIN = 'grain', 'Grains'
        FRUIT = 'fruit', 'Fruits'
        OTHER = 'other', 'Others'

    farm = models.ForeignKey(
        'farms.Farm',
        related_name='crops',
        on_delete=models.CASCADE,
        verbose_name='farm',
    )
    name = models.CharField('crop name', max_length=255)
    category = models.CharField(
        'category',
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    variety = models.CharField('variety', max_length=255, blank=True)
    image = models.ImageField(
        'crop photo',
        upload_to='crops/%Y/%m/',
        blank=True,
        null=True,
        help_text='Photo shown on the crop inventory card.',
    )
    estimated_yield = models.DecimalField(
        'estimated yield (tons per hectare)',
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text='Expected production in tons per hectare.',
    )
    planting_date = models.DateField('planting date', default=timezone.localdate)
    days_to_maturity = models.PositiveIntegerField(
        'days to maturity',
        default=DEFAULT_MATURITY_DAYS,
        validators=[MinValueValidator(1)],
        help_text='Estimated number of days from planting until the crop can be harvested.',
    )
    expected_harvest_date = models.DateField(
        'system-assigned harvest date',
        blank=True,
        null=True,
        help_text='Automatically calculated from the planting date and days to maturity.',
    )
    actual_harvest_date = models.DateField('actual harvest date', blank=True, null=True)
    harvest_season = models.CharField('harvest season', max_length=100, blank=True, default='')
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
    soil_type = models.CharField(
        'soil type',
        max_length=100,
        blank=True,
        default='',
        help_text='Type of soil used for planting (e.g. Clay Loam, Sandy Loam).',
    )
    reference_source = models.CharField(
        'agricultural reference source',
        max_length=255,
        blank=True,
        default='',
        help_text='Official Philippine reference used for crop maturity information.',
    )
    reference_url = models.URLField(
        'agricultural reference URL',
        max_length=500,
        blank=True,
        default='',
        help_text='Direct link to official variety publication or catalog.',
    )
    notes = models.TextField(blank=True)
    quality = models.CharField(
        'quality / grade',
        max_length=30,
        choices=Quality.choices,
        blank=True,
        default='',
        help_text='Quality grade recorded for this crop.',
    )
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

    def generate_harvest_season(self):
        """Auto-generate harvest season based on the assigned harvest date."""
        ref_date = self.expected_harvest_date or self.planting_date
        if not ref_date:
            return ''
        month = ref_date.month
        year = ref_date.year
        # Common Philippine seasons (adjust as needed) - can be customized
        if month in (12, 1, 2, 3, 4, 5):
            return f'Dry Season {year}'
        return f'Wet Season {year}'

    def calculate_expected_harvest_date(self):
        """Return the system-assigned harvest date for the crop."""
        if not self.planting_date:
            return None
        days = self.days_to_maturity or suggest_maturity_days(self.name)
        return self.planting_date + timedelta(days=days)

    def save(self, *args, **kwargs):
        # The harvest date is always assigned by the system; the crop form
        # only collects the planting date and the days to maturity.
        if not self.days_to_maturity:
            self.days_to_maturity = suggest_maturity_days(self.name)
        self.expected_harvest_date = self.calculate_expected_harvest_date()
        self.harvest_season = self.generate_harvest_season()
        super().save(*args, **kwargs)

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
    def is_ready_for_harvest(self):
        """Whether the crop can be harvested right now."""
        if self.actual_harvest_date or self.status in (
            self.Status.HARVESTED,
            self.Status.FAILED,
        ):
            return False
        if self.status == self.Status.READY_FOR_HARVEST:
            return True
        days = self.days_to_harvest
        return days is not None and days <= 0

    @property
    def maturity_status(self):
        """Return the crop's harvest-readiness stage."""
        if self.actual_harvest_date or self.status == self.Status.HARVESTED:
            return 'harvested'
        if self.status == self.Status.FAILED:
            return 'failed'

        if self.is_ready_for_harvest:
            return 'ready'

        days = self.days_to_harvest
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

    @property
    def display_image_url(self):
        """The uploaded crop photo, or the matching stock photo/placeholder.

        Priority order:
        1. This crop's own uploaded image (if any).
        2. The user's saved default image for this crop name (survives deletion
           and re-adding the same crop).
        3. Another crop by the same user with the same name that has an image.
        4. The catalog/placeholder image.

        A saved default is only used while its file still exists. Stale
        records (for example after an image was deleted) are removed and the
        property falls through to the next source, so the page never renders
        a broken image.
        """
        from django.core.files.storage import default_storage

        # 1. This crop's own uploaded image.
        if self.image:
            try:
                if default_storage.exists(self.image.name):
                    return self.image.url
            except Exception:
                pass

        # 2. The user's saved default image for this crop name. The record
        #    stores a storage-relative path, so it must be converted to a URL
        #    (e.g. ``/media/crops/...``) before it is used in templates.
        if self.user_id:
            default_images = CropDefaultImage.objects.filter(
                user_id=self.user_id,
                crop_name__iexact=self.name,
            ).exclude(image_path='')
            for default_img in default_images:
                try:
                    if default_storage.exists(default_img.image_path):
                        return default_storage.url(default_img.image_path)
                except Exception:
                    pass
                # The pointed-at file is gone; remove the stale record.
                default_img.delete()

        # 3. Another crop by the same user with the same name that has an image.
        if self.user_id:
            same_name_crop = (
                Crop.objects.filter(user_id=self.user_id, name__iexact=self.name)
                .exclude(pk=self.pk)
                .exclude(image='')
                .exclude(image__isnull=True)
                .order_by('-created_at')
                .first()
            )
            if same_name_crop and same_name_crop.image:
                try:
                    if default_storage.exists(same_name_crop.image.name):
                        return same_name_crop.image.url
                except Exception:
                    pass

        # 4. Local catalog/placeholder image.
        return static(crop_image_path(self.name))

    @property
    def harvest_progress(self):
        """Percentage of the planting-to-harvest window that has elapsed."""
        if self.actual_harvest_date or self.status == self.Status.HARVESTED:
            return 100
        if not self.planting_date or not self.expected_harvest_date:
            return 0

        total_days = (self.expected_harvest_date - self.planting_date).days
        if total_days <= 0:
            return 100 if timezone.localdate() >= self.expected_harvest_date else 0

        elapsed_days = (timezone.localdate() - self.planting_date).days
        return max(0, min(100, round(elapsed_days / total_days * 100)))


class AgriculturalReference(models.Model):
    """Verified Philippine agricultural crop variety and maturity reference."""

    class Source(models.TextChoices):
        BINHING_PALAY = 'Binhing Palay', 'Binhing Palay (PhilRice)'
        PHILRICE = 'PhilRice', 'Philippine Rice Research Institute (PhilRice)'
        ATI = 'Agricultural Training Institute (ATI)', 'Agricultural Training Institute (ATI)'
        AMTEC = 'UPLB AMTEC', 'UPLB Agricultural Machinery Testing and Evaluation Center (AMTEC)'
        ANEE = 'Anee Crop Varieties', 'Anee Crop Varieties'

    crop_name = models.CharField('crop name', max_length=100, db_index=True)
    category = models.CharField(
        'category',
        max_length=20,
        choices=Crop.Category.choices,
        default=Crop.Category.OTHER,
        db_index=True,
    )
    variety_name = models.CharField('variety name', max_length=255, db_index=True)
    days_to_maturity = models.PositiveIntegerField(
        'days to maturity',
        validators=[MinValueValidator(1)],
        help_text='Official days to maturity according to published agricultural reference.',
    )
    days_to_maturity_min = models.PositiveIntegerField(
        'minimum days to maturity',
        null=True,
        blank=True,
    )
    days_to_maturity_max = models.PositiveIntegerField(
        'maximum days to maturity',
        null=True,
        blank=True,
    )
    source_name = models.CharField('reference source', max_length=150, choices=Source.choices)
    source_url = models.URLField('official reference URL', max_length=500)
    description = models.TextField('characteristics and recommendations', blank=True, default='')
    soil_type = models.CharField('recommended soil type', max_length=100, blank=True, default='')
    irrigation_info = models.CharField('ecosystem / irrigation', max_length=150, blank=True, default='')
    verified_date = models.DateField('verification date', default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblcropagriculturalreferences'
        ordering = ['crop_name', 'variety_name']
        verbose_name = 'agricultural crop reference'
        verbose_name_plural = 'agricultural crop references'

    def __str__(self):
        return f'{self.crop_name} - {self.variety_name} ({self.days_to_maturity} days, {self.source_name})'

