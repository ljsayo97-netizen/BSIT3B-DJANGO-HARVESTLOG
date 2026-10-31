"""Revenue records for crops grown on each hectare."""

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

MONEY_PLACES = Decimal('0.01')


def _money(value):
    """Round a value to two decimal places for storage and display."""
    return Decimal(str(value or 0)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


class Revenue(models.Model):
    """A sale of produce from a crop, used to track revenue per hectare."""

    revenue_code = models.CharField(
        'revenue ID',
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text='Automatically generated revenue reference (e.g. REV-2026-001).',
    )
    crop = models.ForeignKey(
        'crops.Crop',
        related_name='revenues',
        on_delete=models.CASCADE,
        verbose_name='crop',
        help_text='The crop that produced the sale. Its planted area is used to compute revenue per hectare.',
    )
    farm = models.ForeignKey(
        'farms.Farm',
        related_name='revenues',
        on_delete=models.CASCADE,
        verbose_name='farm',
        editable=False,
    )
    sale_date = models.DateField('sale date', default=timezone.localdate)
    quantity_sold = models.DecimalField(
        'quantity sold',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Amount of produce sold.',
    )
    unit = models.CharField(
        'unit',
        max_length=50,
        default='kg',
        help_text='Unit of measure used for the sale (e.g. kg, tons, baskets, sacks).',
    )
    price_per_unit = models.DecimalField(
        'price per unit',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Selling price for one unit, in Philippine pesos.',
    )
    total_revenue = models.DecimalField(
        'total revenue',
        max_digits=14,
        decimal_places=2,
        default=0,
        editable=False,
        help_text='Automatically calculated as quantity sold multiplied by price per unit.',
    )
    buyer = models.CharField(
        'buyer / market',
        max_length=255,
        blank=True,
        help_text='Buyer, trader, or market where the produce was sold (optional).',
    )
    notes = models.TextField('remarks', blank=True, help_text='Notes about the sale.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='revenues',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'tblrevenues'
        ordering = ['-sale_date', '-created_at']
        verbose_name = 'revenue record'
        verbose_name_plural = 'revenue records'

    def __str__(self):
        crop_name = self.crop.name if self.crop_id else 'Crop'
        reference = self.revenue_code or 'Revenue'
        return f'{reference} — {crop_name} ({self.farm.name if self.farm_id else "Farm"})'

    @property
    def area_hectares(self):
        """Planted area of the crop that produced this sale."""
        if not self.crop_id:
            return Decimal('0')
        return Decimal(str(self.crop.area_hectares or 0))

    @property
    def revenue_per_hectare(self):
        """Revenue earned for every hectare planted with this crop."""
        area = self.area_hectares
        if not area:
            return _money(0)
        return _money(Decimal(str(self.total_revenue or 0)) / area)

    @property
    def quantity_per_hectare(self):
        """Quantity sold for every hectare planted with this crop."""
        area = self.area_hectares
        if not area:
            return Decimal('0')
        return (
            Decimal(str(self.quantity_sold or 0)) / area
        ).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

    @property
    def average_price(self):
        """Average selling price per unit for this sale."""
        quantity = Decimal(str(self.quantity_sold or 0))
        if not quantity:
            return _money(0)
        return _money(Decimal(str(self.total_revenue or 0)) / quantity)

    def _next_revenue_code(self):
        """Build the next sequential revenue code for the sale year."""
        year = (self.sale_date or timezone.localdate()).year
        prefix = f'REV-{year}-'
        codes = Revenue.objects.filter(
            revenue_code__startswith=prefix,
        ).values_list('revenue_code', flat=True)

        highest = 0
        for code in codes:
            try:
                highest = max(highest, int(code.rsplit('-', 1)[1]))
            except (AttributeError, IndexError, ValueError):
                continue
        return f'{prefix}{highest + 1:03d}'

    def save(self, *args, **kwargs):
        """Assign system defaults, the farm, total revenue, and a revenue ID."""
        if not self.sale_date:
            self.sale_date = timezone.localdate()
        if self.crop_id:
            self.farm_id = self.crop.farm_id
        if not self.unit:
            self.unit = 'kg'
        self.quantity_sold = _money(self.quantity_sold)
        self.price_per_unit = _money(self.price_per_unit)
        self.total_revenue = _money(
            Decimal(str(self.quantity_sold or 0))
            * Decimal(str(self.price_per_unit or 0))
        )

        if self.revenue_code:
            return super().save(*args, **kwargs)

        for attempt in range(5):
            self.revenue_code = self._next_revenue_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.revenue_code = None
                if attempt == 4:
                    raise
