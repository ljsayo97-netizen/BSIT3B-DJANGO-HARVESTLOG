from django.contrib import admin

from .models import FarmActivity


@admin.register(FarmActivity)
class FarmActivityAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'scheduled_date',
        'activity_type',
        'farm',
        'location',
        'assigned_worker',
        'priority',
        'status',
    )
    list_filter = ('status', 'priority', 'activity_type', 'scheduled_date', 'farm')
    search_fields = ('location', 'assigned_worker', 'remarks', 'farm__name', 'crop__name')
    ordering = ['scheduled_date', 'id']
