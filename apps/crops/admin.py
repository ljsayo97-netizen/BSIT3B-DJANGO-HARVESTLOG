from django.contrib import admin

from .models import Crop, Harvest, Sale


class HarvestInline(admin.TabularInline):
    model = Harvest
    extra = 0


@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ('name', 'variety', 'farm_name', 'owner')
    list_filter = ('farm_name',)
    search_fields = ('name', 'variety', 'farm_name', 'farm_location', 'owner__username')
    inlines = (HarvestInline,)


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = ('crop', 'harvest_date', 'quantity', 'unit')
    list_filter = ('unit', 'harvest_date')
    search_fields = ('crop__name', 'crop__variety', 'crop__owner__username')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('harvest', 'sold_on', 'quantity', 'unit_price', 'total_revenue', 'buyer')
    list_filter = ('sold_on',)
    search_fields = ('harvest__crop__name', 'buyer')
