from django.contrib import admin

from .models import AgriculturalReference, Crop


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'variety',
        'farm',
        'planting_date',
        'days_to_maturity',
        'expected_harvest_date',
        'status',
        'area_hectares',
        'soil_type',
        'reference_source',
    )
    list_filter = ('status', 'planting_date', 'expected_harvest_date', 'reference_source')
    search_fields = ('name', 'variety', 'farm__name', 'notes', 'reference_source')
    list_editable = ('status',)
    readonly_fields = ('expected_harvest_date', 'harvest_season')
    ordering = ['-planting_date']


@admin.register(AgriculturalReference)
class AgriculturalReferenceAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'crop_name',
        'variety_name',
        'category',
        'days_to_maturity',
        'source_name',
        'soil_type',
        'irrigation_info',
        'verified_date',
        'is_active',
    )
    list_filter = ('source_name', 'category', 'is_active', 'verified_date')
    search_fields = ('crop_name', 'variety_name', 'source_name', 'description')
    ordering = ['crop_name', 'variety_name']

