from django.contrib import admin

from .models import Farm


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'farm_code',
        'name',
        'owner',
        'location',
        'email',
        'contact_number',
        'zip_code',
        'size_hectares',
        'date_registered',
        'status',
        'is_deleted',
        'deleted_at',
    )
    list_filter = ('status', 'is_deleted', 'date_registered')
    search_fields = (
        'farm_code',
        'name',
        'owner',
        'location',
        'description',
        'email',
        'contact_number',
        'zip_code',
    )
    list_editable = ('status',)
    ordering = ['-date_registered']

    def get_queryset(self, request):
        return Farm.all_objects.all()
