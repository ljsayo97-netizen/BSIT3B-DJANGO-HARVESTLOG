from django.contrib import admin

from .models import Crop


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'variety',
        'farm',
        'planting_date',
        'expected_harvest_date',
        'status',
        'area_hectares',
    )
    list_filter = ('status', 'planting_date', 'expected_harvest_date')
    search_fields = ('name', 'variety', 'farm__name', 'notes')
    list_editable = ('status',)
    ordering = ['-planting_date']
