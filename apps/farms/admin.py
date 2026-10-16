from django.contrib import admin

from .models import Farm


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'owner',
        'location',
        'size_hectares',
        'date_registered',
        'status',
    )
    list_filter = ('status', 'date_registered')
    search_fields = ('name', 'owner', 'location', 'description')
    list_editable = ('status',)
    ordering = ['-date_registered']
