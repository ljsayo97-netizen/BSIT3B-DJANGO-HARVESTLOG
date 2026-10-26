from django.contrib import admin

from .models import Harvest, HarvestSchedule


@admin.register(HarvestSchedule)
class HarvestScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'scheduled_date',
        'farm',
        'crop',
        'field_name',
        'workers_count',
        'assigned_to',
        'status',
    )
    list_filter = ('status', 'scheduled_date', 'farm')
    search_fields = ('field_name', 'assigned_to', 'supervisor', 'notes', 'farm__name', 'crop__name')
    list_editable = ('status',)
    ordering = ['scheduled_date']


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = (
        'harvest_code',
        'harvest_date',
        'farm',
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
        'location',
        'harvested_by',
        'supervised_by',
        'notes',
        'quality_observations',
        'farm__name',
    )
    list_editable = ('quality_grade',)
    readonly_fields = ('harvest_code',)
    ordering = ['-harvest_date']
