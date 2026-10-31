from django.contrib import admin

from .models import Revenue


@admin.register(Revenue)
class RevenueAdmin(admin.ModelAdmin):
    list_display = (
        'revenue_code',
        'sale_date',
        'farm',
        'crop',
        'quantity_sold',
        'unit',
        'price_per_unit',
        'total_revenue',
        'buyer',
    )
    list_filter = ('sale_date', 'farm', 'unit')
    search_fields = (
        'revenue_code',
        'crop__name',
        'crop__variety',
        'farm__name',
        'buyer',
        'notes',
    )
    readonly_fields = ('revenue_code', 'farm', 'total_revenue')
    ordering = ['-sale_date', '-created_at']
