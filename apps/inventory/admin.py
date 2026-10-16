from django.contrib import admin

from .models import InventoryItem, InventoryTransaction


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'product_name',
        'variety',
        'quantity',
        'unit',
        'storage_location',
        'minimum_stock_level',
        'status',
        'created_at',
    )
    list_filter = ('status', 'unit', 'created_at')
    search_fields = ('product_name', 'variety', 'storage_location', 'notes')
    list_editable = ('status',)
    ordering = ['-created_at']


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'inventory_item',
        'transaction_type',
        'quantity',
        'unit',
        'previous_quantity',
        'new_quantity',
        'transaction_date',
        'performed_by',
    )
    list_filter = ('transaction_type', 'transaction_date')
    search_fields = (
        'inventory_item__product_name',
        'reason',
        'performed_by',
        'notes',
    )
    ordering = ['-transaction_date']
