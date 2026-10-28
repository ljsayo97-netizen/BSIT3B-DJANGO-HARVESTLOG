from django.contrib import admin

from .models import Harvest, HarvestNotification


@admin.register(HarvestNotification)
class HarvestNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'crop',
        'kind',
        'expected_harvest_date',
        'is_read',
        'created_at',
    )
    list_filter = ('kind', 'is_read', 'expected_harvest_date')
    search_fields = ('crop__name', 'crop__farm__name', 'message')
    list_editable = ('is_read',)
    readonly_fields = ('message', 'created_at', 'read_at')
    ordering = ['-created_at']


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = (
        'harvest_code',
        'harvest_date',
        'farm',
        'crop',
        'crop_type',
        'quantity_harvested',
        'unit',
        'quality_grade',
        'workers_count',
        'harvested_by',
    )
    list_filter = ('quality_grade', 'harvest_date', 'farm')
    search_fields = (
        'harvest_code',
        'crop_type',
        'crop__name',
        'location',
        'harvested_by',
        'supervised_by',
        'notes',
        'quality_observations',
        'farm__name',
    )
    list_editable = ('quality_grade',)
    readonly_fields = ('harvest_code', 'harvest_date', 'harvest_season')
    ordering = ['-harvest_date']
