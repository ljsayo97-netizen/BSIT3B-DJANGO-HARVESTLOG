from django.contrib import admin

from .models import Harvest


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'harvest_date',
        'farm',
        'crop_type',
        'quantity_harvested',
        'unit',
        'quality_grade',
        'harvested_by',
    )
    list_filter = ('quality_grade', 'harvest_date', 'farm')
    search_fields = ('crop_type', 'location', 'harvested_by', 'supervised_by', 'notes', 'farm__name')
    list_editable = ('quality_grade',)
    ordering = ['-harvest_date']
