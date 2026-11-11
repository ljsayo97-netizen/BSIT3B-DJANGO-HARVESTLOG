"""Harvest calendar page view."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

from .services import (
    SOURCE_ACTIVITIES,
    SOURCE_ALL,
    SOURCE_CHOICES,
    SOURCE_HARVESTS,
    SOURCE_KEYS,
    build_calendar_context,
)

SOURCE_ICONS = {
    SOURCE_ALL: 'fas fa-layer-group',
    SOURCE_HARVESTS: 'fas fa-wheat-awn',
    SOURCE_ACTIVITIES: 'fas fa-list-check',
}


def _parse_id(raw_value):
    raw_value = (raw_value or '').strip()
    return int(raw_value) if raw_value.isdigit() else None


def _source_links(request, source):
    """Build the dropdown links that switch what the calendar displays.

    Any other active filters (farm/crop) are kept so switching the content
    type never silently resets the rest of the view.
    """
    base_url = reverse('harvest_calendar:calendar')
    links = []
    for value, label in SOURCE_CHOICES:
        params = request.GET.copy()
        params['show'] = value
        links.append({
            'value': value,
            'label': label,
            'icon': SOURCE_ICONS.get(value, 'fas fa-calendar-days'),
            'url': f'{base_url}?{params.urlencode()}',
            'active': value == source,
        })
    return links


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
        'source_links': _source_links(request, source),
        'today': timezone.localdate(),
    })
    return render(request, 'harvest_calendar/list.html', context)
