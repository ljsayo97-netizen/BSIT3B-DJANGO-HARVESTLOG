"""Global search used by the topbar search box."""

from django.db.models import Q
from django.urls import reverse
from django.utils.http import urlencode

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.revenue.models import Revenue

RESULT_LIMIT = 6
MAX_QUERY_LENGTH = 100
SEPARATOR = ' · '


def _format_date(value):
    """Format a date for a compact result meta line."""
    return value.strftime('%b %d, %Y') if value else ''


def _format_number(value):
    """Drop trailing zeros from a decimal for display."""
    if value is None:
        return '0'
    return f'{value:,.2f}'.rstrip('0').rstrip('.')


def _join(parts):
    """Join the non-empty parts with a visual separator."""
    return SEPARATOR.join(part for part in parts if part)


def _view_all_url(url_name, query, **params):
    """Build a module list URL pre-filtered with the search term."""
    params = {key: value for key, value in params.items() if value is not None and value != ''}
    params['q'] = query
    return f'{reverse(url_name)}?{urlencode(params)}'


def _farm_results(user, query):
    """Match the user's farms by name, owner, location, or farm ID."""
    queryset = Farm.objects.filter(
        Q(name__icontains=query)
        | Q(owner__icontains=query)
        | Q(location__icontains=query)
        | Q(farm_code__icontains=query)
        | Q(email__icontains=query)
        | Q(description__icontains=query),
        user=user,
    ).order_by('name')
    total = queryset.count()

    items = [
        {
            'title': farm.name,
            'subtitle': _join((farm.owner, farm.location)),
            'meta': _join((
                farm.farm_code,
                f'{farm.size_hectares} ha' if farm.size_hectares is not None else '',
            )),
            'badge': farm.get_status_display(),
            'url': _view_all_url('farms:farm_list', farm.name),
        }
        for farm in queryset[:RESULT_LIMIT]
    ]
    return items, total, _view_all_url('farms:farm_list', query)


def _crop_results(user, query):
    """Match the user's crops by name, variety, farm, or notes."""
    queryset = Crop.objects.filter(
        Q(name__icontains=query)
        | Q(variety__icontains=query)
        | Q(farm__name__icontains=query)
        | Q(notes__icontains=query),
        user=user,
    ).select_related('farm').order_by('-planting_date', '-id')
    total = queryset.count()

    items = [
        {
            'title': _join((crop.name, crop.variety)),
            'subtitle': _join((crop.farm.name, crop.get_status_display())),
            'meta': _join((
                f'Planted {_format_date(crop.planting_date)}' if crop.planting_date else '',
                f'{_format_number(crop.area_hectares)} ha',
            )),
            'badge': crop.get_status_display(),
            'url': _view_all_url(
                'crops:crop_list',
                crop.name,
                farm=crop.farm_id,
            ),
        }
        for crop in queryset[:RESULT_LIMIT]
    ]
    return items, total, _view_all_url('crops:crop_list', query)


def _activity_results(user, query):
    """Match the user's scheduled activities by location, worker, or remarks."""
    queryset = FarmActivity.objects.filter(
        Q(location__icontains=query)
        | Q(assigned_worker__icontains=query)
        | Q(remarks__icontains=query)
        | Q(activity_type__icontains=query)
        | Q(farm__name__icontains=query)
        | Q(crop__name__icontains=query),
        user=user,
    ).select_related('farm', 'crop').order_by('scheduled_date', 'id')
    total = queryset.count()

    items = [
        {
            'title': _join((activity.get_activity_type_display(), activity.location)),
            'subtitle': _join((
                activity.farm.name,
                activity.crop.name if activity.crop_id else '',
            )),
            'meta': _join((
                _format_date(activity.scheduled_date),
                activity.assigned_worker,
                activity.get_status_display(),
            )),
            'badge': activity.get_priority_display(),
            'url': _view_all_url('activities:activity_list', activity.location),
        }
        for activity in queryset[:RESULT_LIMIT]
    ]
    return items, total, _view_all_url('activities:activity_list', query)


def _harvest_results(user, query):
    """Match the user's harvest records by ID, crop, farm, or location."""
    queryset = Harvest.objects.filter(
        Q(harvest_code__icontains=query)
        | Q(crop_type__icontains=query)
        | Q(location__icontains=query)
        | Q(harvested_by__icontains=query)
        | Q(supervised_by__icontains=query)
        | Q(notes__icontains=query)
        | Q(farm__name__icontains=query)
        | Q(crop__name__icontains=query),
        user=user,
    ).select_related('farm', 'crop').order_by('-harvest_date', '-id')
    total = queryset.count()

    items = [
        {
            'title': harvest.harvest_code or harvest.crop_type or 'Harvest record',
            'subtitle': _join((harvest.crop_type, harvest.farm.name)),
            'meta': _join((
                _format_date(harvest.harvest_date),
                (
                    f'{_format_number(harvest.quantity_harvested)} {harvest.unit}'
                    if harvest.quantity_harvested is not None
                    else ''
                ),
                harvest.location,
            )),
            'badge': harvest.get_quality_grade_display() if harvest.quality_grade else '',
            'url': _view_all_url(
                'harvests:harvest_list',
                harvest.harvest_code or harvest.crop_type or query,
            ),
        }
        for harvest in queryset[:RESULT_LIMIT]
    ]
    return items, total, _view_all_url('harvests:harvest_list', query)


def _revenue_results(user, query):
    """Match the user's revenue records by ID, crop, farm, or buyer."""
    queryset = Revenue.objects.filter(
        Q(revenue_code__icontains=query)
        | Q(crop__name__icontains=query)
        | Q(crop__variety__icontains=query)
        | Q(farm__name__icontains=query)
        | Q(buyer__icontains=query)
        | Q(notes__icontains=query),
        user=user,
    ).select_related('farm', 'crop').order_by('-sale_date', '-id')
    total = queryset.count()

    items = [
        {
            'title': _join((
                revenue.revenue_code or 'Revenue record',
                revenue.crop.name if revenue.crop_id else '',
            )),
            'subtitle': _join((revenue.farm.name, revenue.buyer)),
            'meta': _join((
                _format_date(revenue.sale_date),
                f'\u20b1{_format_number(revenue.total_revenue)}',
                f'{_format_number(revenue.quantity_sold)} {revenue.unit}',
            )),
            'badge': '',
            'url': _view_all_url(
                'revenue:revenue_list',
                revenue.revenue_code or query,
            ),
        }
        for revenue in queryset[:RESULT_LIMIT]
    ]
    return items, total, _view_all_url('revenue:revenue_list', query)


SEARCH_GROUP_BUILDERS = (
    ('farms', 'Farms', 'fas fa-tractor', _farm_results),
    ('crops', 'Crops', 'fas fa-seedling', _crop_results),
    ('activities', 'Activities', 'fas fa-clipboard-list', _activity_results),
    ('harvests', 'Harvests', 'fas fa-wheat-awn', _harvest_results),
    ('revenue', 'Revenue', 'fas fa-coins', _revenue_results),
)


def build_global_search_context(user, query):
    """Return grouped search results for the topbar search page."""
    query = (query or '').strip()[:MAX_QUERY_LENGTH]
    groups = []
    total_results = 0

    if query:
        for key, label, icon, builder in SEARCH_GROUP_BUILDERS:
            items, total, view_all_url = builder(user, query)
            groups.append({
                'key': key,
                'label': label,
                'icon': icon,
                'items': items,
                'total': total,
                'view_all_url': view_all_url,
            })
            total_results += total

    return {
        'query': query,
        'global_search_query': query,
        'search_groups': groups,
        'total_results': total_results,
    }
