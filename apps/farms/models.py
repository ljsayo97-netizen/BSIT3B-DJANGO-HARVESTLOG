"""Farm registration and management models."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Farm(models.Model):
    """A registered farm."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        ARCHIVED = 'archived', 'Archived'

    name = models.CharField('farm name', max_length=255)
    owner = models.CharField('owner / manager', max_length=255)
    location = models.CharField(max_length=255)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='farms',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblfarms'
        ordering = ['-date_registered']
        verbose_name = 'farm'
        verbose_name_plural = 'farms'

    def __str__(self):
        return self.name
