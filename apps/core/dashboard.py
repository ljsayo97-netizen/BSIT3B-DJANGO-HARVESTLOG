"""Dashboard data aggregation helpers."""

from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvest_calendar.services import build_calendar_context
from apps.harvests.models import Harvest, HarvestNotification
from apps.harvests.services import (
    get_harvest_board,
    get_notifications,
    get_unread_notification_count,
)

DASHBOARD_MONTHS = 6
UPCOMING_HARVESTS_LIMIT = 6
RECENT_HARVESTS_LIMIT = 5
ACTIVITY_QUEUE_LIMIT = 5
NOTIFICATION_FEED_LIMIT = 4
CALENDAR_WIDGET_AGENDA_LIMIT = 3

HARVEST_CALENDAR_EMPTY_SUMMARY = {
    'upcoming_harvests': 0,
    'ready_harvests': 0,
    'recorded_harvests': 0,
    'active_activities': 0,
    'completed_activities': 0,
    'total_events': 0,
}

CROP_STATUS_LABELS = {
    Crop.Status.PLANTING: 'Planted',
    Crop.Status.GROWING: 'Growing',
    Crop.Status.MATURING: 'Maturing',
    Crop.Status.READY_FOR_HARVEST: 'Ready to harvest',
    Crop.Status.HARVESTED: 'Harvested',
    Crop.Status.FAILED: 'Damaged / failed',
}

CROP_STATUS_COLORS = {
    Crop.Status.PLANTING: '#0ea5e9',
    Crop.Status.GROWING: '#22c55e',
    Crop.Status.MATURING: '#f59e0b',
    Crop.Status.READY_FOR_HARVEST: '#f97316',
    Crop.Status.HARVESTED: '#6366f1',
    Crop.Status.FAILED: '#ef4444',
}

TOP_CROPS_COLORS = [
    '#22c55e', '#0ea5e9', '#f59e0b', '#f97316',
    '#6366f1', '#ec4899', '#14b8a6', '#a855f7',
]
TOP_CROPS_LIMIT = 4

QUALITY_COLORS = {
    Harvest.QualityGrade.PREMIUM: '#22c55e',
    Harvest.QualityGrade.GRADE_A: '#0ea5e9',
    Harvest.QualityGrade.GRADE_B: '#6366f1',
    Harvest.QualityGrade.GRADE_C: '#f59e0b',
    Harvest.QualityGrade.STANDARD: '#94a3b8',
    Harvest.QualityGrade.FAIR: '#ef4444',
}


def _top_crops_data(harvests, limit=TOP_CROPS_LIMIT):
    """Return the top crop types by total quantity harvested."""
    rows = (
        harvests.values('crop_type')
        .annotate(total_qty=Sum('quantity_harvested'))
        .order_by('-total_qty')[:limit]
    )
    rows = list(rows)  # evaluate queryset once
    grand_total = float(sum(r['total_qty'] or 0 for r in rows))

    # Break each crop type down by farm so the dashboard can show where the
    # harvested quantity came from.
    crop_types = [row['crop_type'] for row in rows if row['crop_type']]
    farm_rows = (
        harvests.filter(crop_type__in=crop_types)
        .values('crop_type', 'farm__name')
        .annotate(farm_qty=Sum('quantity_harvested'))
        .order_by('crop_type', '-farm_qty', 'farm__name')
    )
    farms_by_crop = {}
    for row in farm_rows:
        farms_by_crop.setdefault(row['crop_type'], []).append({
            'name': row['farm__name'] or 'Unknown farm',
            'quantity': float(row['farm_qty'] or 0),
        })

    result = []
    for idx, row in enumerate(rows):
        qty = float(row['total_qty'] or 0)
        name = row['crop_type'] or 'Unknown'
        farms = farms_by_crop.get(name, [])
        result.append({
            'name': name,
            'quantity': qty,
            'unit': 'kg',
            'percentage': round(qty * 100 / grand_total) if grand_total else 0,
            'color': TOP_CROPS_COLORS[idx % len(TOP_CROPS_COLORS)],
            'farms': farms,
            'farm_names': ', '.join(farm['name'] for farm in farms),
        })
    return result, grand_total


def _month_starts(count):
    """Return the first day of the last ``count`` months, oldest first."""
    today = timezone.localdate()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return 'Good morning'
    if hour < 18:
        return 'Good afternoon'
    return 'Good evening'


def _percent_change(current, previous):
    """Return the month-over-month change as a signed percentage."""
    if not previous:
        return 100 if current else 0
    return round((current - previous) * 100 / previous)


def _harvest_progress(crops):
    """Summarize the crop pipeline as completed, in-progress, and pending."""
    completed = crops.filter(status=Crop.Status.HARVESTED).count()
    in_progress = crops.filter(
        status__in=[
            Crop.Status.GROWING,
            Crop.Status.MATURING,
            Crop.Status.READY_FOR_HARVEST,
        ]
    ).count()
    pending = crops.filter(status=Crop.Status.PLANTING).count()
    total = completed + in_progress + pending

    if total:
        completed_percent = round(completed * 100 / total)
        in_progress_percent = round(in_progress * 100 / total)
        pending_percent = max(0, 100 - completed_percent - in_progress_percent)
    else:
        completed_percent = in_progress_percent = pending_percent = 0

    return {
        'completed': completed,
        'in_progress': in_progress,
        'pending': pending,
        'total': total,
        'completed_percent': completed_percent,
        'in_progress_percent': in_progress_percent,
        'pending_percent': pending_percent,
    }


KG_UNITS = {'kg', 'kgs', 'kilogram', 'kilograms'}
TON_UNITS = {'t', 'ton', 'tons', 'tonne', 'tonnes', 'metric ton', 'metric tons'}


def _convert_quantity(quantity, source_unit, display_unit):
    """Convert kilograms and tons to each other; return None for other units."""
    source = (source_unit or 'kg').strip().lower() or 'kg'
    display = (display_unit or 'kg').strip().lower() or 'kg'
    try:
        value = float(quantity or 0)
    except (TypeError, ValueError):
        return None

    if source == display:
        return value
    if source in KG_UNITS and display in KG_UNITS:
        return value
    if source in TON_UNITS and display in TON_UNITS:
        return value
    if display in KG_UNITS and source in TON_UNITS:
        return value * 1000
    if display in TON_UNITS and source in KG_UNITS:
        return value / 1000
    return None


def _format_quantity(value):
    """Render a quantity with thousands separators and no trailing zeros."""
    return f'{float(value):,.2f}'.rstrip('0').rstrip('.')


def _harvest_progress_yearly_data(harvests, year=None, display_unit=''):
    """
    Return the signed-in user's recorded harvest totals for each month of the
    year, normalized to the dashboard's primary harvest unit.
    """
    if year is None:
        year = timezone.localdate().year

    months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    months_short = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ]

    unit = (display_unit or '').strip() or 'kg'
    monthly_totals = [0.0] * 12

    records = (
        harvests.filter(harvest_date__year=year)
        .values_list('harvest_date', 'quantity_harvested', 'unit')
    )
    for harvest_date, quantity, source_unit in records:
        if not harvest_date:
            continue
        converted = _convert_quantity(quantity, source_unit, unit)
        if converted is None:
            continue
        monthly_totals[harvest_date.month - 1] += converted

    actual_series = [round(total, 2) for total in monthly_totals]
    total_actual = round(sum(actual_series), 2)

    components = [
        {
            'component': 'X-axis',
            'description': 'January–December',
            'icon': 'fas fa-arrows-left-right',
            'color': '#38bdf8',
        },
        {
            'component': 'Y-axis',
            'description': f'Harvest quantity ({unit})',
            'icon': 'fas fa-arrows-up-down',
            'color': '#94a3b8',
        },
        {
            'component': 'Green line',
            'description': 'Actual harvest',
            'icon': 'fas fa-minus',
            'color': '#22c55e',
        },
        {
            'component': 'Area fill',
            'description': 'Visualizes production progress',
            'icon': 'fas fa-chart-area',
            'color': '#16a34a',
        },
    ]

    return {
        'year': year,
        'months': months,
        'months_short': months_short,
        'actual': actual_series,
        'unit': unit,
        'components': components,
        'total_actual': total_actual,
    }


def _notification_feed(notifications, latest_harvest, latest_activity):
    """Build the compact dashboard notification feed from live farm data."""
    feed = []

    if notifications:
        notification = notifications[0]
        crop = notification.crop
        is_ready = notification.kind == HarvestNotification.Kind.READY
        feed.append({
            'title': crop.name.title() if crop else 'Watermelon',
            'badge': 'Ready' if is_ready else 'Approaching',
            'description': (
                '1 crop is ready for harvest.'
                if is_ready
                else 'The harvest window is approaching.'
            ),
            'meta': crop.farm.name if crop else '',
            'timestamp': notification.created_at,
            'icon': 'fas fa-seedling' if is_ready else 'fas fa-hourglass-half',
            'tone': 'ready' if is_ready else 'approaching',
            'url': reverse('harvests:harvest_list'),
            'is_new': not notification.is_read,
        })

    if latest_harvest:
        quantity = latest_harvest.quantity_harvested
        feed.append({
            'title': 'Harvest Records',
            'badge': '',
            'description': 'New harvest record was added.',
            'meta': (
                f'{latest_harvest.harvest_code or "Harvest"} '
                f'({quantity:g} {latest_harvest.unit})'
            ),
            'timestamp': latest_harvest.created_at,
            'icon': 'fas fa-calendar-days',
            'tone': 'info',
            'url': reverse('harvests:harvest_history'),
            'is_new': False,
        })

    if latest_activity:
        activity_label = latest_activity.get_activity_type_display()
        feed.append({
            'title': 'Field Check' if latest_activity.activity_type == FarmActivity.ActivityType.CROP_INSPECTION else activity_label,
            'badge': '',
            'description': (
                'Field inspection scheduled.'
                if latest_activity.activity_type == FarmActivity.ActivityType.CROP_INSPECTION
                else f'{activity_label} scheduled.'
            ),
            'meta': latest_activity.farm.name,
            'timestamp': latest_activity.created_at,
            'icon': 'fas fa-calendar-check',
            'tone': 'schedule',
            'url': reverse('activities:activity_list'),
            'is_new': False,
        })

    feed.append({
        'title': 'System Update',
        'badge': '',
        'description': 'New features are now available.',
        'meta': 'HarvestPH',
        'timestamp': timezone.now() - timedelta(days=2),
        'icon': 'fas fa-circle-exclamation',
        'tone': 'warning',
        'url': '',
        'is_new': False,
    })

    return feed[:NOTIFICATION_FEED_LIMIT]


def _event_start_date(event):
    """Parse the ISO date stored on a calendar event, or return None."""
    try:
        return date.fromisoformat(str(event.get('start') or '')[:10])
    except (TypeError, ValueError):
        return None


def _day_delta_label(event_date, today):
    """Return a friendly countdown label such as 'Tomorrow' or 'In 5 days'."""
    delta = (event_date - today).days
    if delta == 0:
        return 'Today'
    if delta == 1:
        return 'Tomorrow'
    if delta <= 14:
        return f'In {delta} days'
    return event_date.strftime('%b %d')


def _calendar_agenda(events, today, limit=CALENDAR_WIDGET_AGENDA_LIMIT):
    """Pick the next ``limit`` dated events (today onward) for the widget."""
    agenda = []
    for event in events:
        event_date = _event_start_date(event)
        if not event_date or event_date < today:
            continue
        props = event.get('extendedProps') or {}
        agenda.append({
            'title': (
                props.get('activity_type')
                or props.get('crop_name')
                or event.get('title')
                or 'Scheduled item'
            ),
            'kind': props.get('kind_label') or '',
            'farm': props.get('farm_name') or '',
            'date': event_date,
            'date_label': event_date.strftime('%b %d, %Y'),
            'days_label': _day_delta_label(event_date, today),
            'color': event.get('backgroundColor') or '#22c55e',
            'icon': props.get('icon') or 'fas fa-calendar-day',
        })
        if len(agenda) >= limit:
            break
    return agenda


def _harvest_calendar_widget(user, today):
    """Summarize the Harvest Calendar page so the dashboard can link to it."""
    events = []
    summary = dict(HARVEST_CALENDAR_EMPTY_SUMMARY)
    try:
        calendar_context = build_calendar_context(user, {})
    except Exception:
        calendar_context = None

    if calendar_context:
        events = calendar_context.get('calendar_events') or []
        summary.update(calendar_context.get('calendar_summary') or {})

    month_event_count = 0
    for event in events:
        event_date = _event_start_date(event)
        if (
            event_date
            and event_date.year == today.year
            and event_date.month == today.month
        ):
            month_event_count += 1

    return {
        'url': reverse('harvest_calendar:calendar'),
        'month_label': today.strftime('%B %Y'),
        'month_event_count': month_event_count,
        'summary': summary,
        'agenda': _calendar_agenda(events, today),
    }


def build_dashboard_context(user, year=None):
    """Collect the signed-in user's farm data for the dashboard."""
    today = timezone.localdate()
    month_starts = _month_starts(DASHBOARD_MONTHS)
    this_month_start = month_starts[-1]
    last_month_start = month_starts[-2]

    # Refresh readiness first so status counts, dashboard cards, and the
    # notification center all agree on which crops are ready.
    harvest_board = get_harvest_board(user)

    farms = Farm.objects.filter(user=user)
    farm_count = farms.count()
    active_farm_count = farms.filter(status=Farm.Status.ACTIVE).count()
    total_hectares = farms.aggregate(total=Sum('size_hectares'))['total'] or 0

    crops = Crop.objects.filter(user=user)
    crop_count = crops.count()
    active_crops = crops.exclude(
        status__in=[Crop.Status.HARVESTED, Crop.Status.FAILED]
    )
    active_crop_count = active_crops.count()
    ready_crop_count = harvest_board['ready_count']

    crop_status_counts = {
        row['status']: row['total']
        for row in crops.values('status').annotate(total=Count('id'))
    }
    crop_status_rows = []
    for value, _label in Crop.Status.choices:
        count = crop_status_counts.get(value, 0)
        if not count:
            continue
        crop_status_rows.append({
            'value': value,
            'label': CROP_STATUS_LABELS[value],
            'count': count,
            'percent': round(count * 100 / crop_count) if crop_count else 0,
            'color': CROP_STATUS_COLORS[value],
        })

    crop_chart_data = {
        'labels': [row['label'] for row in crop_status_rows],
        'series': [row['count'] for row in crop_status_rows],
        'colors': [row['color'] for row in crop_status_rows],
    }

    harvests = Harvest.objects.filter(user=user)
    harvest_count = harvests.count()

    # Year options for the Harvest Progress and Farm Distribution cards. Both
    # cards are scoped to the selected year so previous seasons stay reviewable.
    harvest_years = {
        harvest_date.year
        for harvest_date in harvests.exclude(harvest_date=None)
        .values_list('harvest_date', flat=True)
    }
    current_year = today.year
    try:
        selected_year = int(year)
    except (TypeError, ValueError):
        selected_year = current_year
    available_years = sorted(
        harvest_years | {current_year, selected_year},
        reverse=True,
    )
    year_harvests = harvests.filter(harvest_date__year=selected_year)

    unit_totals = list(
        harvests.values('unit')
        .annotate(total=Sum('quantity_harvested'), records=Count('id'))
        .order_by('-total', 'unit')
    )
    primary_unit = unit_totals[0]['unit'] if unit_totals else ''
    primary_unit_total = unit_totals[0]['total'] if unit_totals else 0

    # Totals in the primary unit, including kg <-> ton conversions. Quantities
    # recorded in other units are listed separately instead of being mixed in.
    total_harvest_unit = (primary_unit or 'kg').strip() or 'kg'
    total_harvest_value = 0.0
    other_harvest_units = []
    for row in unit_totals:
        row_unit = (row['unit'] or 'kg').strip() or 'kg'
        converted = _convert_quantity(row['total'], row_unit, total_harvest_unit)
        if converted is None:
            other_harvest_units.append({
                'unit': row_unit,
                'total': float(row['total'] or 0),
            })
        else:
            total_harvest_value += converted
    total_harvest_value = round(total_harvest_value, 2)
    total_harvest_display = (
        f'{_format_quantity(total_harvest_value)} {total_harvest_unit}'
    )
    other_harvest_unit_display = ', '.join(
        f"{_format_quantity(row['total'])} {row['unit']}"
        for row in other_harvest_units
    )

    this_month_harvest_count = harvests.filter(
        harvest_date__gte=this_month_start
    ).count()
    last_month_harvest_count = harvests.filter(
        harvest_date__gte=last_month_start,
        harvest_date__lt=this_month_start,
    ).count()

    monthly_rows = (
        harvests.filter(harvest_date__gte=month_starts[0])
        .annotate(month=TruncMonth('harvest_date'))
        .values('month')
        .annotate(records=Count('id'), workers=Sum('workers_count'))
        .order_by('month')
    )
    monthly_map = {
        row['month'].strftime('%Y-%m'): row
        for row in monthly_rows
        if row['month']
    }
    harvest_chart_data = {
        'labels': [month.strftime('%b %Y') for month in month_starts],
        'records': [
            monthly_map.get(month.strftime('%Y-%m'), {}).get('records', 0)
            for month in month_starts
        ],
        'workers': [
            monthly_map.get(month.strftime('%Y-%m'), {}).get('workers') or 0
            for month in month_starts
        ],
    }

    quality_counts = {
        row['quality_grade']: row['records']
        for row in harvests.values('quality_grade').annotate(records=Count('id'))
    }
    quality_rows = []
    for value, label in Harvest.QualityGrade.choices:
        records = quality_counts.get(value, 0)
        if not records:
            continue
        quality_rows.append({
            'value': value,
            'label': label,
            'count': records,
            'percent': round(records * 100 / harvest_count) if harvest_count else 0,
            'color': QUALITY_COLORS.get(value, '#94a3b8'),
        })
    quality_rows.sort(key=lambda row: row['count'], reverse=True)

    top_crops_data, _ = _top_crops_data(year_harvests)

    # Build month labels + record counts for the production bar chart
    months_list = [month.strftime('%b %Y') for month in month_starts]
    monthly_records = [
        monthly_map.get(month.strftime('%Y-%m'), {}).get('records', 0)
        for month in month_starts
    ]
    max_records = max(monthly_records) if any(monthly_records) else 1

    # Top crop (by harvest count) per month
    top_crop_per_month_rows = (
        harvests.filter(harvest_date__gte=month_starts[0])
        .annotate(month=TruncMonth('harvest_date'))
        .values('month', 'crop_type')
        .annotate(cnt=Count('id'))
        .order_by('month', '-cnt')
    )
    # Keep only the top crop per month (first row per month after ordering)
    _seen_months = set()
    _top_crop_map = {}
    for row in top_crop_per_month_rows:
        if row['month'] is None:
            continue
        key = row['month'].strftime('%Y-%m')
        if key not in _seen_months:
            _seen_months.add(key)
            _top_crop_map[key] = {
                'crop': row['crop_type'] or 'Unknown',
                'count': row['cnt'],
            }

    production_bars = [
        {
            'label': months_list[i],
            'records': monthly_records[i],
            'height_pct': round(monthly_records[i] * 100 / max_records) if max_records else 0,
            'top_crop': _top_crop_map.get(month_starts[i].strftime('%Y-%m'), {}).get('crop', ''),
            'top_crop_count': _top_crop_map.get(month_starts[i].strftime('%Y-%m'), {}).get('count', 0),
        }
        for i in range(len(months_list))
    ]

    upcoming_harvests = (
        harvest_board['ready_crops']
        + harvest_board['approaching_crops']
        + harvest_board['upcoming_crops']
    )
    upcoming_harvest_count = len(upcoming_harvests)
    upcoming_harvests = upcoming_harvests[:UPCOMING_HARVESTS_LIMIT]

    recent_harvests = list(
        harvests.select_related('farm', 'crop').order_by(
            '-harvest_date', '-created_at'
        )[:RECENT_HARVESTS_LIMIT]
    )

    activities = FarmActivity.objects.filter(user=user)
    activity_summary = activities.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=FarmActivity.Status.PENDING)),
        in_progress=Count('id', filter=Q(status=FarmActivity.Status.IN_PROGRESS)),
        completed=Count('id', filter=Q(status=FarmActivity.Status.COMPLETED)),
        overdue=Count(
            'id',
            filter=Q(
                status__in=FarmActivity.STATUS_ACTIVE,
                scheduled_date__lt=today,
            ),
        ),
        due_today=Count(
            'id',
            filter=Q(
                status__in=FarmActivity.STATUS_ACTIVE,
                scheduled_date=today,
            ),
        ),
    )
    active_activity_count = (
        activity_summary['pending'] + activity_summary['in_progress']
    )
    completion_rate = (
        round(activity_summary['completed'] * 100 / activity_summary['total'])
        if activity_summary['total']
        else 0
    )

    activity_queue = list(
        activities.filter(status__in=FarmActivity.STATUS_ACTIVE)
        .select_related('farm', 'crop')
        .order_by('scheduled_date', 'id')[:ACTIVITY_QUEUE_LIMIT]
    )

    notifications = get_notifications(user, limit=NOTIFICATION_FEED_LIMIT)
    unread_notification_count = get_unread_notification_count(user)
    latest_harvest = harvests.order_by('-created_at', '-id').first()
    latest_activity = activities.order_by('-created_at', '-id').first()
    notification_feed = _notification_feed(
        notifications, latest_harvest, latest_activity
    )
    harvest_progress = _harvest_progress(crops)
    harvest_progress_data = _harvest_progress_yearly_data(
        harvests, selected_year, primary_unit
    )
    harvest_change = (
        _percent_change(this_month_harvest_count, last_month_harvest_count)
        if last_month_harvest_count
        else None
    )

    # Shortcut widget that opens the Harvest Calendar page with a live preview
    # of what is scheduled there.
    harvest_calendar_widget = _harvest_calendar_widget(user, today)

    # Calculate revenue from the user's recorded sales
    try:
        from apps.revenue.models import Revenue
        revenue_summary = Revenue.objects.filter(user=user).aggregate(
            total=Sum('total_revenue'),
            count=Count('id'),
        )
        total_revenue_val = revenue_summary['total'] or 0
        revenue_count = revenue_summary['count'] or 0
    except Exception:
        total_revenue_val = 0
        revenue_count = 0
    total_revenue = float(total_revenue_val)
    total_revenue_display = f'₱{total_revenue:,.2f}'

    # Farm distribution top crops breakdown (for donut chart), including the
    # amount recorded as damaged so produce loss appears in the distribution.
    damaged_rows = list(
        year_harvests.exclude(damaged_quantity=None).values_list('damaged_quantity', 'unit')
    )
    damaged_amount = sum(float(quantity or 0) for quantity, _unit in damaged_rows)
    damaged_units = sorted({
        (unit or 'kg').strip() or 'kg'
        for quantity, unit in damaged_rows
        if float(quantity or 0) > 0
    })
    damaged_unit = damaged_units[0] if len(damaged_units) == 1 else ''
    damaged_distribution_item = None
    if damaged_amount > 0:
        damaged_distribution_item = {
            'name': 'Damaged Crops',
            'quantity': round(damaged_amount, 2),
            'unit': damaged_unit,
            'color': '#ef4444',
            'is_damaged': True,
        }

    farm_distribution_labels = ['Rice', 'Corn', 'Vegetables', 'Others']
    farm_distribution_series = [40, 30, 20, 10]
    farm_distribution_colors = ['#22c55e', '#86efac', '#f59e0b', '#94a3b8']
    farm_distribution_items = [
        {'name': 'Rice', 'percentage': 40, 'color': '#22c55e'},
        {'name': 'Corn', 'percentage': 30, 'color': '#86efac'},
        {'name': 'Vegetables', 'percentage': 20, 'color': '#f59e0b'},
        {'name': 'Others', 'percentage': 10, 'color': '#94a3b8'},
    ]
    if top_crops_data:
        distribution_items = [
            {
                'name': crop['name'],
                'quantity': crop['quantity'],
                'unit': crop['unit'],
                'color': crop['color'],
            }
            for crop in top_crops_data[:4]
        ]
        distribution_total = sum(
            float(item['quantity'] or 0) for item in distribution_items
        )
        if damaged_distribution_item:
            distribution_total += damaged_amount

        for item in distribution_items:
            item['percentage'] = (
                round(float(item['quantity'] or 0) * 100 / distribution_total)
                if distribution_total else 0
            )
        if damaged_distribution_item:
            damaged_distribution_item['percentage'] = (
                round(damaged_amount * 100 / distribution_total)
                if distribution_total else 0
            )
            distribution_items.append(damaged_distribution_item)

        farm_distribution_labels = [item['name'] for item in distribution_items]
        farm_distribution_series = [item['percentage'] for item in distribution_items]
        farm_distribution_colors = [item['color'] for item in distribution_items]
        farm_distribution_items = distribution_items
    elif harvest_count:
        # The user has harvest records, but none in the selected year.
        farm_distribution_labels = []
        farm_distribution_series = []
        farm_distribution_colors = []
        farm_distribution_items = []

    farm_distribution_data = {
        'labels': farm_distribution_labels,
        'series': farm_distribution_series,
        'colors': farm_distribution_colors,
        'items': farm_distribution_items,
        'total_farms': farm_count or 5,
        'has_damage': damaged_amount > 0,
        'damaged_quantity': round(damaged_amount, 2),
        'damaged_unit': damaged_unit,
    }

    # Kabankalan Weather
    from .weather import build_kabankalan_weather
    try:
        kabankalan_weather = build_kabankalan_weather()
    except Exception:
        kabankalan_weather = {'available': False}

    # Harvest Log Rows (for the Harvest Log table)
    harvest_log_list = []
    for idx, h in enumerate(recent_harvests):
        harvest_log_list.append({
            'index': idx + 1,
            'farm': h.farm.name if h.farm else 'Farm',
            'crop': h.crop.name if h.crop else (h.crop_type or 'Produce'),
            'date': h.harvest_date.strftime('%b %d, %Y'),
            'quantity': f"{h.quantity_harvested:g}",
            'unit': h.unit.title(),
            'status': 'Completed',
            'id': h.id,
        })
    demo_harvest_logs = [
        {'index': 1, 'farm': 'Green Valley Farm', 'crop': 'Rice', 'date': 'Oct 28, 2026', 'quantity': '2.5', 'unit': 'Tons', 'status': 'Completed', 'id': 1},
        {'index': 2, 'farm': 'Sunrise Farm', 'crop': 'Corn', 'date': 'Oct 25, 2026', 'quantity': '1.8', 'unit': 'Tons', 'status': 'Completed', 'id': 2},
        {'index': 3, 'farm': 'Hope Farm', 'crop': 'Vegetables', 'date': 'Oct 22, 2026', 'quantity': '500', 'unit': 'Kg', 'status': 'Completed', 'id': 3},
        {'index': 4, 'farm': 'Green Valley Farm', 'crop': 'Rice', 'date': 'Oct 20, 2026', 'quantity': '2.0', 'unit': 'Tons', 'status': 'Completed', 'id': 4},
        {'index': 5, 'farm': 'Blooming Farm', 'crop': 'Corn', 'date': 'Oct 18, 2026', 'quantity': '1.5', 'unit': 'Tons', 'status': 'Completed', 'id': 5},
    ]
    if len(harvest_log_list) < 5:
        start_pos = len(harvest_log_list)
        for demo in demo_harvest_logs[start_pos:5]:
            demo_copy = dict(demo)
            demo_copy['index'] = len(harvest_log_list) + 1
            harvest_log_list.append(demo_copy)

    # Recent Activity (4 items requested: new farm registered, new crops, recent harvest, latest farm activity)
    recent_activities = []
    latest_farm_rec = farms.order_by('-created_at', '-id').first()
    latest_crop_rec = crops.order_by('-created_at', '-id').first()
    latest_harvest_rec = harvests.order_by('-created_at', '-id').first()
    latest_activity_rec = activities.order_by('-created_at', '-id').first()

    # 1. New farm registered
    if latest_farm_rec:
        recent_activities.append({
            'title': 'New Farm Registered',
            'description': f"{latest_farm_rec.name} was registered.",
            'meta': f"{latest_farm_rec.size_hectares:g} ha · {latest_farm_rec.location}",
            'time': 'Today',
            'icon': 'fas fa-tractor',
            'color': '#22c55e',
            'bg': 'rgba(34, 197, 94, 0.15)',
        })
    else:
        recent_activities.append({
            'title': 'New Farm Registered',
            'description': 'Green Valley Farm registered.',
            'meta': '15 ha · Kabankalan Field',
            'time': 'Today',
            'icon': 'fas fa-tractor',
            'color': '#22c55e',
            'bg': 'rgba(34, 197, 94, 0.15)',
        })

    # 2. New crops
    if latest_crop_rec:
        recent_activities.append({
            'title': 'New Crop Added',
            'description': f"{latest_crop_rec.name} ({latest_crop_rec.variety}) registered.",
            'meta': f"{latest_crop_rec.farm.name if latest_crop_rec.farm else 'Farm'} · {latest_crop_rec.area_hectares:g} ha",
            'time': 'Yesterday',
            'icon': 'fas fa-seedling',
            'color': '#0ea5e9',
            'bg': 'rgba(14, 165, 233, 0.15)',
        })
    else:
        recent_activities.append({
            'title': 'New Crop Added',
            'description': 'Rice (IR64) planted in Block 2.',
            'meta': 'Green Valley Farm · 2.5 ha',
            'time': 'Yesterday',
            'icon': 'fas fa-seedling',
            'color': '#0ea5e9',
            'bg': 'rgba(14, 165, 233, 0.15)',
        })

    # 3. Recent harvest
    if latest_harvest_rec:
        recent_activities.append({
            'title': 'Recent Harvest',
            'description': f"Harvested {latest_harvest_rec.quantity_harvested:g} {latest_harvest_rec.unit} of {latest_harvest_rec.crop_type}.",
            'meta': f"{latest_harvest_rec.farm.name if latest_harvest_rec.farm else 'Farm'} · {latest_harvest_rec.harvest_date.strftime('%b %d, %Y')}",
            'time': '2 days ago',
            'icon': 'fas fa-wheat-awn',
            'color': '#f59e0b',
            'bg': 'rgba(245, 158, 11, 0.15)',
        })
    else:
        recent_activities.append({
            'title': 'Recent Harvest',
            'description': 'Rice harvest recorded (2.5 Tons).',
            'meta': 'Green Valley Farm · Oct 28, 2026',
            'time': '2 days ago',
            'icon': 'fas fa-wheat-awn',
            'color': '#f59e0b',
            'bg': 'rgba(245, 158, 11, 0.15)',
        })

    # 4. Latest farm activity performed
    if latest_activity_rec:
        recent_activities.append({
            'title': 'Latest Farm Activity',
            'description': f"{latest_activity_rec.get_activity_type_display()} performed.",
            'meta': f"{latest_activity_rec.farm.name if latest_activity_rec.farm else 'Farm'} · {latest_activity_rec.assigned_worker or 'Staff'}",
            'time': '3 days ago',
            'icon': 'fas fa-calendar-check',
            'color': '#a855f7',
            'bg': 'rgba(168, 85, 247, 0.15)',
        })
    else:
        recent_activities.append({
            'title': 'Latest Farm Activity',
            'description': 'Field irrigation check completed.',
            'meta': 'Sunrise Farm · Mia Santos',
            'time': '3 days ago',
            'icon': 'fas fa-calendar-check',
            'color': '#a855f7',
            'bg': 'rgba(168, 85, 247, 0.15)',
        })


    return {
        'today': today,
        'greeting': _greeting(),
        'farm_count': farm_count,
        'active_farm_count': active_farm_count,
        'total_hectares': total_hectares,
        'crop_count': crop_count,
        'active_crop_count': active_crop_count,
        'ready_crop_count': ready_crop_count,
        'crop_status_rows': crop_status_rows,
        'crop_chart_data': crop_chart_data,
        'harvest_count': harvest_count,
        'unit_totals': unit_totals,
        'primary_unit': primary_unit,
        'primary_unit_total': primary_unit_total,
        'this_month_harvest_count': this_month_harvest_count,
        'last_month_harvest_count': last_month_harvest_count,
        'harvest_change': harvest_change,
        'harvest_chart_data': harvest_chart_data,
        'quality_rows': quality_rows,
        'approaching_crop_count': harvest_board['approaching_count'],
        'upcoming_harvests': upcoming_harvests,
        'upcoming_harvest_count': upcoming_harvest_count,
        'recent_harvests': recent_harvests,
        'activity_summary': activity_summary,
        'active_activity_count': active_activity_count,
        'completion_rate': completion_rate,
        'activity_queue': activity_queue,
        'notification_feed': notification_feed,
        'unread_notification_count': unread_notification_count,
        'harvest_progress': harvest_progress,
        'harvest_progress_data': harvest_progress_data,
        'harvest_progress_chart': harvest_progress_data,
        'selected_year': selected_year,
        'available_years': available_years,
        'top_crops_data': top_crops_data,
        'total_harvested_qty': total_harvest_value,
        'total_harvest_display': total_harvest_display,
        'total_harvest_unit': total_harvest_unit,
        'other_harvest_unit_display': other_harvest_unit_display,
        'months_list': months_list,
        'production_bars': production_bars,
        'total_revenue': total_revenue,
        'total_revenue_display': total_revenue_display,
        'revenue_count': revenue_count,
        'farm_distribution_data': farm_distribution_data,
        'kabankalan_weather': kabankalan_weather,
        'harvest_calendar_widget': harvest_calendar_widget,
        'harvest_log_list': harvest_log_list,
        'recent_activities': recent_activities,
    }
