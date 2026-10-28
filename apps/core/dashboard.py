"""Dashboard data aggregation helpers."""

from datetime import date

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.harvests.services import get_harvest_board

DASHBOARD_MONTHS = 6
UPCOMING_HARVESTS_LIMIT = 6
RECENT_HARVESTS_LIMIT = 5
ACTIVITY_QUEUE_LIMIT = 5

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

QUALITY_COLORS = {
    Harvest.QualityGrade.PREMIUM: '#22c55e',
    Harvest.QualityGrade.GRADE_A: '#0ea5e9',
    Harvest.QualityGrade.GRADE_B: '#6366f1',
    Harvest.QualityGrade.GRADE_C: '#f59e0b',
    Harvest.QualityGrade.STANDARD: '#94a3b8',
    Harvest.QualityGrade.FAIR: '#ef4444',
}


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


def build_dashboard_context(user):
    """Collect the signed-in user's farm data for the dashboard."""
    today = timezone.localdate()
    month_starts = _month_starts(DASHBOARD_MONTHS)
    this_month_start = month_starts[-1]
    last_month_start = month_starts[-2]

    # Refresh readiness first so status counts, dashboard cards, and the
    # notification banner all agree on which crops are ready.
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

    unit_totals = list(
        harvests.values('unit')
        .annotate(total=Sum('quantity_harvested'), records=Count('id'))
        .order_by('-total', 'unit')
    )
    primary_unit = unit_totals[0]['unit'] if unit_totals else ''
    primary_unit_total = unit_totals[0]['total'] if unit_totals else 0

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
    }
