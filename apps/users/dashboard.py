"""Farmer dashboard data helper.

Computes all statistics displayed on the farmer dashboard
from the existing database tables. Queries are scoped to
the authenticated farmer (request.user).
"""


def build_farmer_dashboard_context(user):
    """Return a context dict with all data needed for the farmer dashboard."""

    from datetime import timedelta

    from django.db.models import Sum
    from django.db.models.functions import TruncMonth
    from django.utils import timezone

    from apps.activities.models import FarmActivity
    from apps.crops.models import Crop
    from apps.farms.models import Farm
    from apps.harvests.models import Harvest
    from apps.revenue.models import Revenue

    # My Farms
    farms = Farm.objects.filter(user=user).order_by('-created_at')
    farms_count = farms.count()

    # Active Crops (not harvested, not failed)
    active_crops = Crop.objects.filter(user=user).exclude(
        status__in=[Crop.Status.HARVESTED, Crop.Status.FAILED]
    ).select_related('farm').order_by('-planting_date')
    active_crops_count = active_crops.count()

    # Total Harvest (kg harvested from tblharvests)
    total_harvest = Harvest.objects.filter(user=user).aggregate(
        total=Sum('quantity_harvested')
    )['total'] or 0

    # Estimated Revenue from tblrevenues
    total_revenue = Revenue.objects.filter(user=user).aggregate(
        total=Sum('total_revenue')
    )['total'] or 0

    # Recent Harvest Records (last 5)
    recent_harvests = Harvest.objects.filter(user=user).select_related(
        'farm', 'crop'
    ).order_by('-created_at')[:5]

    # Upcoming Farm Activities (latest activity)
    latest_activity = FarmActivity.objects.filter(user=user).select_related(
        'farm', 'crop'
    ).order_by('-created_at').first()

    # Harvest Summary Chart data (monthly production last 6 months)
    today = timezone.localdate()
    current_year = today.year
    cutoff = today - timedelta(days=180)  # last 6 months

    # Years available in the grower's harvest records, newest first.
    years = sorted(
        {
            value.year
            for value in Harvest.objects.filter(user=user)
            .values_list('harvest_date', flat=True)
            if value
        },
        reverse=True,
    )
    if current_year not in years:
        years.insert(0, current_year)

    monthly_data = (
        Harvest.objects.filter(user=user, created_at__gte=cutoff)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total_kg=Sum('quantity_harvested'))
        .order_by('month')
    )
    chart_labels = []
    chart_data = []
    for item in monthly_data:
        # Convert the month start date to an abbreviated MM/YY display.
        month = item['month']
        try:
            month_name = f'{month.month:02d}/{str(month.year)[-2:]}'
            chart_labels.append(month_name)
            chart_data.append(float(item['total_kg']) if item['total_kg'] else 0)
        except (AttributeError, TypeError):
            continue

    # Ensure we have exactly 6 labels/data points for the chart
    while len(chart_labels) < 6:
        chart_labels.insert(0, '')
        chart_data.insert(0, 0)
    chart_labels = chart_labels[-6:]
    chart_data = chart_data[-6:]

    # Get the user's name for the welcome message
    user_name = user.get_full_name() or user.username

    return {
        'farms': farms,
        'farms_count': farms_count,
        'active_crops': active_crops,
        'active_crops_count': active_crops_count,
        'total_harvest': total_harvest,
        'total_revenue': total_revenue,
        'recent_harvests': recent_harvests,
        'latest_activity': latest_activity,
        'current_year': current_year,
        'years': years,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'user_name': user_name,
    }