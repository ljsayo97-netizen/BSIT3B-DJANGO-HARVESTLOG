"""Hectare monitoring metrics.

Every figure on the Hectare Monitoring page is derived live from the farms and
crops the signed-in farmer already registered. No extra tables are required.

The page answers four questions:

* how much land the farmer owns in total,
* how much of that land is currently planted,
* how much land is still available, and
* whether any farm is approaching (or over) its registered capacity.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Sum
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

HECTARE_PLACES = Decimal('0.01')
PERCENT_PLACES = Decimal('0.1')

# A farm is flagged as approaching capacity at 60% utilisation and as over
# capacity at 90% (or whenever crop allocation exceeds the registered size).
APPROACHING_CAPACITY_PERCENT = Decimal('60')
OVER_CAPACITY_PERCENT = Decimal('90')

UPCOMING_HARVEST_DAYS = 30
ALLOCATION_ROW_LIMIT = 5

CROP_STATUSES_RELEASING_LAND = (Crop.Status.HARVESTED, Crop.Status.FAILED)

STATUS_META = {
    'normal': {
        'key': 'normal',
        'label': 'Normal',
        'badge_class': 'hm-badge--green',
        'color': '#16a34a',
        'icon': 'fa-circle-check',
    },
    'approaching': {
        'key': 'approaching',
        'label': 'Approaching Capacity',
        'badge_class': 'hm-badge--amber',
        'color': '#d97706',
        'icon': 'fa-triangle-exclamation',
    },
    'critical': {
        'key': 'critical',
        'label': 'Over Capacity',
        'badge_class': 'hm-badge--red',
        'color': '#dc2626',
        'icon': 'fa-circle-exclamation',
    },
}

ALLOCATION_COLORS = (
    '#16a34a',
    '#22c55e',
    '#4ade80',
    '#65a30d',
    '#84cc16',
    '#14b8a6',
)


def _decimal(value):
    """Convert a value to Decimal without raising on None/blank strings."""
    try:
        return Decimal(str(value if value is not None else 0))
    except (TypeError, ValueError):
        return Decimal('0')


def _hectares(value):
    """Quantise a hectare amount to two decimal places."""
    return _decimal(value).quantize(HECTARE_PLACES, rounding=ROUND_HALF_UP)


def format_hectares(value):
    """Render a hectare amount without unnecessary trailing zeros."""
    amount = _hectares(value)
    text = f'{amount:,.2f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _percentage(part, total):
    """Return ``part`` as a percentage of ``total`` rounded to one decimal."""
    total = _decimal(total)
    if not total:
        return Decimal('0.0')
    return (
        _decimal(part) * Decimal('100') / total
    ).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)


def format_percentage(value):
    """Render a percentage with exactly one decimal place."""
    return f'{_decimal(value).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP):.1f}'


def _clamped_percentage(value):
    """Return a 0-100 percentage string suitable for CSS widths."""
    percentage = _decimal(value)
    if percentage < 0:
        percentage = Decimal('0')
    if percentage > 100:
        percentage = Decimal('100')
    return format_percentage(percentage)


def _status_for(utilization, used_area, total_area):
    """Return the capacity status for a utilisation percentage."""
    if _decimal(total_area) <= 0:
        return STATUS_META['normal']
    if _decimal(used_area) > _decimal(total_area) or utilization >= OVER_CAPACITY_PERCENT:
        return STATUS_META['critical']
    if utilization >= APPROACHING_CAPACITY_PERCENT:
        return STATUS_META['approaching']
    return STATUS_META['normal']


def _usage_split(used_area, total_area):
    """Return used/available amounts, capping available at zero."""
    used = _hectares(used_area)
    total = _hectares(total_area)
    available = total - used
    if available < 0:
        available = Decimal('0')
    return used, available


def _farm_alert(row):
    """Build the capacity alert shown beside the farm utilisation table."""
    status = row['status']
    used = _decimal(row['used_area_raw'])
    total = _decimal(row['total_area_raw'])
    available = _decimal(row['available_area_raw'])
    utilization = _decimal(row['utilization'])

    if total <= 0:
        message = 'Set the farm size to enable hectare monitoring.'
    elif status['key'] == 'critical':
        if used > total:
            message = (
                f'Crop allocation exceeds the registered area by '
                f'{format_hectares(used - total)} ha. Adjust crop areas or '
                'update the farm size.'
            )
        else:
            message = (
                f'Only {format_hectares(available)} ha available. Avoid '
                'adding more crops until land is cleared.'
            )
    elif status['key'] == 'approaching':
        message = (
            f'Your farm is {format_percentage(utilization)}% utilized. '
            'Consider planning for next season.'
        )
    elif available > 0:
        message = (
            f'Only {format_hectares(available)} ha available. '
            'Avoid exceeding the limit.'
        )
    else:
        message = 'No unallocated land remains on this farm.'

    return {
        'farm_id': row['id'],
        'farm_name': row['name'],
        'message': message,
        'status': status,
        'status_label': status['label'],
        'badge_class': status['badge_class'],
        'color': status['color'],
        'icon': status['icon'],
        'sort_priority': {'critical': 0, 'approaching': 1, 'normal': 2}[status['key']],
    }


def _allocation_rows(active_crops):
    """Group current crop allocations by crop name."""
    grouped = {}
    for crop in active_crops:
        name = (crop.name or 'Unnamed crop').strip() or 'Unnamed crop'
        key = name.lower()
        entry = grouped.setdefault(key, {
            'name': name,
            'area': Decimal('0'),
            'count': 0,
        })
        entry['area'] += _decimal(crop.area_hectares)
        entry['count'] += 1

    total_used = sum((entry['area'] for entry in grouped.values()), Decimal('0'))
    entries = sorted(
        grouped.values(),
        key=lambda entry: (-entry['area'], entry['name'].lower()),
    )

    visible = entries[:ALLOCATION_ROW_LIMIT]
    extras = entries[ALLOCATION_ROW_LIMIT:]
    rows = []

    for index, entry in enumerate(visible):
        percentage = _percentage(entry['area'], total_used)
        rows.append({
            'name': entry['name'],
            'area': format_hectares(entry['area']),
            'percentage': format_percentage(percentage),
            'width': _clamped_percentage(percentage),
            'color': ALLOCATION_COLORS[index % len(ALLOCATION_COLORS)],
            'status_label': 'Active',
            'badge_class': 'hm-badge--green',
            'title': f"{entry['count']} crop record{'s' if entry['count'] != 1 else ''}",
        })

    if extras:
        extra_area = sum((entry['area'] for entry in extras), Decimal('0'))
        extra_count = sum(entry['count'] for entry in extras)
        percentage = _percentage(extra_area, total_used)
        names = ', '.join(entry['name'] for entry in extras[:4])
        if len(extras) > 4:
            names += f' and {len(extras) - 4} more'
        rows.append({
            'name': 'Others',
            'area': format_hectares(extra_area),
            'percentage': format_percentage(percentage),
            'width': _clamped_percentage(percentage),
            'color': ALLOCATION_COLORS[len(visible) % len(ALLOCATION_COLORS)],
            'status_label': 'Active',
            'badge_class': 'hm-badge--green',
            'title': names,
        })

    return rows


def build_hectare_monitoring_context(user):
    """Return all data needed to render the hectare monitoring page."""
    farms = list(Farm.objects.filter(user=user).order_by('name'))
    farm_ids = [farm.id for farm in farms]

    crops = Crop.objects.filter(user=user, farm_id__in=farm_ids)
    active_crops = list(
        crops.exclude(status__in=CROP_STATUSES_RELEASING_LAND)
        .select_related('farm')
        .order_by('name')
    )

    used_by_farm = {}
    for row in (
        crops.exclude(status__in=CROP_STATUSES_RELEASING_LAND)
        .values('farm_id')
        .annotate(total=Sum('area_hectares'))
    ):
        used_by_farm[row['farm_id']] = _decimal(row['total'])

    farm_rows = []
    total_area = Decimal('0')
    used_area = Decimal('0')
    for farm in farms:
        farm_total = _decimal(farm.size_hectares)
        farm_used = used_by_farm.get(farm.id, Decimal('0'))
        used, available = _usage_split(farm_used, farm_total)
        utilization = _percentage(farm_used, farm_total)
        status = _status_for(utilization, farm_used, farm_total)

        total_area += farm_total
        used_area += farm_used

        farm_rows.append({
            'id': farm.id,
            'name': farm.name,
            'location': farm.location,
            'farm_code': farm.farm_code,
            'total_area_raw': farm_total,
            'used_area_raw': farm_used,
            'available_area_raw': available,
            'total_area': format_hectares(farm_total),
            'used_area': format_hectares(farm_used),
            'available_area': format_hectares(available),
            'utilization': utilization,
            'utilization_display': format_percentage(utilization),
            'utilization_width': _clamped_percentage(utilization),
            'status': status,
            'status_label': status['label'],
            'status_badge_class': status['badge_class'],
            'status_color': status['color'],
            'status_icon': status['icon'],
        })

    total_used, total_available = _usage_split(used_area, total_area)
    overall_utilization = _percentage(used_area, total_area)
    overall_status = _status_for(overall_utilization, used_area, total_area)

    # Sort critical/approaching alerts first, then by utilisation descending.
    utilisation_by_farm = {row['id']: row['utilization'] for row in farm_rows}
    alerts = sorted(
        (_farm_alert(row) for row in farm_rows),
        key=lambda alert: (
            alert['sort_priority'],
            -utilisation_by_farm.get(alert['farm_id'], Decimal('0')),
        ),
    )

    today = timezone.localdate()
    upcoming_cutoff = today + timedelta(days=UPCOMING_HARVEST_DAYS)
    upcoming_harvests = (
        crops.exclude(status__in=CROP_STATUSES_RELEASING_LAND)
        .filter(
            expected_harvest_date__gte=today,
            expected_harvest_date__lte=upcoming_cutoff,
        )
        .count()
    )

    varieties = {
        (crop.variety or '').strip().lower()
        for crop in crops.only('variety')
        if (crop.variety or '').strip()
    }

    return {
        'farms': farms,
        'farm_count': len(farms),
        'farm_rows': farm_rows,
        'total_area': format_hectares(total_area),
        'used_area': format_hectares(total_used),
        'available_area': format_hectares(total_available),
        'remaining_percentage': format_percentage(
            _percentage(total_available, total_area)
        ),
        'land_utilization': format_percentage(overall_utilization),
        'land_utilization_width': _clamped_percentage(overall_utilization),
        'land_utilization_status': overall_status,
        'utilization_status_label': overall_status['label'],
        'utilization_status_class': overall_status['badge_class'],
        'utilization_color': overall_status['color'],
        'land_capacity_alerts': alerts,
        'alert_count': len(alerts),
        'crop_allocation': _allocation_rows(active_crops),
        'quick_stats': {
            'total_crops': crops.count(),
            'varieties': len(varieties),
            'farms': len(farms),
            'upcoming_harvests': upcoming_harvests,
        },
        'upcoming_window_days': UPCOMING_HARVEST_DAYS,
    }
