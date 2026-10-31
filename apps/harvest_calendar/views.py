"""Harvest calendar page view."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

from .services import (
    SOURCE_ALL,
    SOURCE_CHOICES,
    SOURCE_KEYS,
    build_calendar_context,
)


def _parse_id(raw_value):
    raw_value = (raw_value or '').strip()
    return int(raw_value) if raw_value.isdigit() else None


@login_required(login_url='login')
def harvest_calendar_page(request):
    """Display harvest dates and scheduled activities on one calendar."""
    farms = Farm.objects.filter(user=request.user).order_by('name')

    farm_id = _parse_id(request.GET.get('farm'))
    if farm_id and not farms.filter(pk=farm_id).exists():
        farm_id = None

    crops = Crop.objects.filter(user=request.user).select_related('farm')
    if farm_id:
        crops = crops.filter(farm_id=farm_id)
    crops = crops.order_by('farm__name', 'name')

    crop_id = _parse_id(request.GET.get('crop'))
    if crop_id and not crops.filter(pk=crop_id).exists():
        crop_id = None

    source = request.GET.get('show', SOURCE_ALL).strip()
    if source not in SOURCE_KEYS:
        source = SOURCE_ALL

    filters = {
        'farm_id': farm_id,
        'crop_id': crop_id,
        'source': source,
    }
    context = build_calendar_context(request.user, filters)
    context.update({
        'farms': farms,
        'crops': crops,
        'farm_id': farm_id,
        'crop_id': crop_id,
        'source': source,
        'source_label': dict(SOURCE_CHOICES)[source],
        'source_choices': SOURCE_CHOICES,
        'today': timezone.localdate(),
    })
    return render(request, 'harvest_calendar/list.html', context)
