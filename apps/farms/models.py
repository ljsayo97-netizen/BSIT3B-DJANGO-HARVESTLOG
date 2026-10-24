"""Farm registration and management models."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class FarmManager(models.Manager):
    """Default manager that hides farms moved to the deleted log."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Farm(models.Model):
    """A registered farm."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ARCHIVED = 'archived', 'Archived'

    name = models.CharField('farm name', max_length=255)
    owner = models.CharField('owner / manager', max_length=255)
    location = models.CharField(max_length=255)
    farm_code = models.CharField(
        'farm ID',
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
        help_text='Auto-generated farm ID, for example FARM-0001.',
    )
    email = models.EmailField('email', blank=True)
    contact_number = models.CharField(
        'contact number',
        max_length=50,
        blank=True,
        help_text='Contact number of the farm owner or manager.',
    )
    zip_code = models.CharField('ZIP code', max_length=20, blank=True)
    size_hectares = models.DecimalField(
        'size (hectares)',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Farm size in hectares.',
    )
    description = models.TextField(blank=True)
    date_registered = models.DateTimeField('date registered')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Moves the farm to the deleted log without removing related records.',
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='farms',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    objects = FarmManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'tblfarms'
        ordering = ['-date_registered']
        verbose_name = 'farm'
        verbose_name_plural = 'farms'
        default_manager_name = 'objects'
        base_manager_name = 'all_objects'

    def __str__(self):
        return self.name

    @staticmethod
    def make_farm_code(pk):
        """Build the auto-generated farm ID, e.g. FARM-0001."""
        return f'FARM-{pk:04d}'

    def save(self, *args, **kwargs):
        """Assign an auto-generated farm ID the first time a farm is stored."""
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.farm_code:
            self.farm_code = self.make_farm_code(self.pk)
            super().save(update_fields=['farm_code'])

    def soft_delete(self):
        """Move the farm to the deleted log while preserving related records."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        """Restore a farm from the deleted log."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
