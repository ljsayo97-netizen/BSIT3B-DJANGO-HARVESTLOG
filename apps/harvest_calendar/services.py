"""Calendar aggregation for crop harvest dates and farm activities.

The calendar is intentionally derived from the existing crop, harvest, and
activity records. This keeps a single source of truth: when a crop is added or
edited, its system-assigned harvest date appears on the calendar automatically.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.harvests.models import Harvest


SOURCE_ALL = 'all'
SOURCE_HARVESTS = 'harvests'
SOURCE_ACTIVITIES = 'activities'
SOURCE_CHOICES = (
    (SOURCE_ALL, 'Harvests & activities'),
    (SOURCE_HARVESTS, 'Harvests only'),
    (SOURCE_ACTIVITIES, 'Activities only'),
)
SOURCE_KEYS = {choice[0] for choice in SOURCE_CHOICES}

HARVEST_WINDOW_DAYS = 30
AGENDA_LIMIT = 6

COLORS = {
    'harvest_expected': '#0ea5e9',
    'harvest_approaching': '#f59e0b',
    'harvest_ready': '#ef4444',
    'harvest_recorded': '#22c55e',
    'activity_pending': '#64748b',
    'activity_progress': '#6366f1',
    'activity_completed': '#14b8a6',
}

LEGEND = (
    {'label': 'Expected harvest', 'color': COLORS['harvest_expected'], 'category': 'harvest'},
    {'label': 'Approaching harvest', 'color': COLORS['harvest_approaching'], 'category': 'harvest'},
    {'label': 'Ready for harvest', 'color': COLORS['harvest_ready'], 'category': 'harvest'},
    {'label': 'Harvest recorded', 'color': COLORS['harvest_recorded'], 'category': 'harvest'},
    {'label': 'Activity pending', 'color': COLORS['activity_pending'], 'category': 'activity'},
    {'label': 'Activity in progress', 'color': COLORS['activity_progress'], 'category': 'activity'},
    {'label': 'Activity completed', 'color': COLORS['activity_completed'], 'category': 'activity'},
)

ACTIVITY_STATUS_VARIANTS = {
    FarmActivity.Status.PENDING: ('pending', 'activity_pending', 'bg-secondary-lt text-secondary'),
    FarmActivity.Status.IN_PROGRESS: ('progress', 'activity_progress', 'bg-primary-lt text-primary'),
    FarmActivity.Status.COMPLETED: ('completed', 'activity_completed', 'bg-success-lt text-success'),
}


def legend_for(source):
    """Return only the legend items that can appear in the current view."""
    if source == SOURCE_HARVESTS:
        return tuple(item for item in LEGEND if item['category'] == 'harvest')
    if source == SOURCE_ACTIVITIES:
        return tuple(item for item in LEGEND if item['category'] == 'activity')
    return LEGEND


def _date_label(value):
    return value.strftime('%b %d, %Y') if value else ''


def _completed_label(value):
    if not value:
        return ''
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime('%b %d, %Y %I:%M %p')


def _event(
    *,
    event_id,
    title,
    start,
    color,
    classes,
    icon,
    badge_class,
    extended_props,
):
    """Build a FullCalendar-compatible event dictionary."""
    return {
        'id': event_id,
        'title': title,
        'start': start.isoformat(),
        'allDay': True,
        'backgroundColor': color,
        'borderColor': color,
        'textColor': '#ffffff',
        'classNames': ['hc-event', *classes],
        'extendedProps': {
            'icon': icon,
            'badge_class': badge_class,
            **extended_props,
        },
    }


def _crop_event(crop, *, recorded=False):
    """Build an expected or recorded harvest event for a crop."""
    if recorded:
        start = crop.actual_harvest_date or crop.expected_harvest_date
        if not start:
            return None
        variant = 'recorded'
        return _event(
            event_id=f'crop-{crop.pk}',
            title=f'Harvest recorded: {crop.name}',
            start=start,
            color=COLORS['harvest_recorded'],
            classes=['hc-harvest', 'hc-recorded'],
            icon='fas fa-clipboard-check',
            badge_class='bg-success-lt text-success',
            extended_props={
                'kind': 'harvest_recorded',
                'kind_label': 'Harvest recorded',
                'crop_id': crop.pk,
                'crop_name': crop.name,
                'variety': crop.variety or 'No variety',
                'farm_name': crop.farm.name,
                'area_label': f'{crop.area_hectares:.2f} ha',
                'date_label': _date_label(start),
                'status_key': 'harvested',
                'status_label': 'Harvested',
                'days_label': '',
                'notes': crop.notes or '',
                'url': reverse('harvests:harvest_history'),
            },
        )

    if not crop.expected_harvest_date:
        return None

    status = crop.maturity_status
    if status == 'ready':
        variant = 'ready'
        color = COLORS['harvest_ready']
        icon = 'fas fa-triangle-exclamation'
        badge_class = 'bg-danger-lt text-danger'
        kind_label = 'Ready for harvest'
    elif status == 'approaching':
        variant = 'approaching'
        color = COLORS['harvest_approaching']
        icon = 'fas fa-hourglass-half'
        badge_class = 'bg-warning-lt text-warning'
        kind_label = 'Approaching harvest'
    else:
        variant = 'expected'
        color = COLORS['harvest_expected']
        icon = 'fas fa-seedling'
        badge_class = 'bg-info-lt text-info'
        kind_label = 'Expected harvest'

    return _event(
        event_id=f'crop-{crop.pk}',
        title=f'Harvest expected: {crop.name}',
        start=crop.expected_harvest_date,
        color=color,
        classes=['hc-harvest', f'hc-{variant}'],
        icon=icon,
        badge_class=badge_class,
        extended_props={
            'kind': 'harvest_expected',
            'kind_label': kind_label,
            'crop_id': crop.pk,
            'crop_name': crop.name,
            'variety': crop.variety or 'No variety',
            'farm_name': crop.farm.name,
            'area_label': f'{crop.area_hectares:.2f} ha',
            'date_label': _date_label(crop.expected_harvest_date),
            'status_key': status,
            'status_label': crop.maturity_label,
            'days_label': crop.days_to_harvest_label,
            'notes': crop.notes or '',
            'url': reverse('crops:crop_list'),
        },
    )


def _harvest_event(harvest):
    """Build a calendar event for a saved harvest record."""
    crop_name = harvest.crop.name if harvest.crop else (harvest.crop_type or 'Crop')
    return _event(
        event_id=f'harvest-{harvest.pk}',
        title=f'Harvest recorded: {crop_name}',
        start=harvest.harvest_date,
        color=COLORS['harvest_recorded'],
        classes=['hc-harvest', 'hc-recorded'],
        icon='fas fa-clipboard-check',
        badge_class='bg-success-lt text-success',
        extended_props={
            'kind': 'harvest_recorded',
            'kind_label': 'Harvest recorded',
            'harvest_id': harvest.pk,
            'harvest_code': harvest.harvest_code or '',
            'crop_id': harvest.crop_id,
            'crop_name': crop_name,
            'variety': (
                harvest.crop.variety
                if harvest.crop and harvest.crop.variety
                else 'No variety'
            ),
            'farm_name': harvest.farm.name,
            'area_label': (
                f'{harvest.crop.area_hectares:.2f} ha' if harvest.crop else ''
            ),
            'quantity_label': f'{harvest.quantity_harvested:,.2f} {harvest.unit}',
            'quality_label': harvest.get_quality_grade_display(),
            'worker': harvest.harvested_by,
            'date_label': _date_label(harvest.harvest_date),
            'status_key': 'harvested',
            'status_label': 'Harvested',
            'days_label': '',
            'notes': harvest.notes or '',
            'url': reverse('harvests:harvest_history'),
        },
    )


def _activity_event(activity):
    """Build a calendar event for a scheduled farm activity."""
    variant, color_key, badge_class = ACTIVITY_STATUS_VARIANTS.get(
        activity.status,
        ACTIVITY_STATUS_VARIANTS[FarmActivity.Status.PENDING],
    )
    return _event(
        event_id=f'activity-{activity.pk}',
        title=f'{activity.get_activity_type_display()} — {activity.location}',
        start=activity.scheduled_date,
        color=COLORS[color_key],
        classes=['hc-activity', f'hc-activity-{variant}'],
        icon=activity.icon,
        badge_class=badge_class,
        extended_props={
            'kind': 'activity',
            'kind_label': 'Farm activity',
            'activity_id': activity.pk,
            'activity_type': activity.get_activity_type_display(),
            'crop_id': activity.crop_id,
            'crop_name': activity.crop.name if activity.crop else '',
            'farm_name': activity.farm.name,
            'location': activity.location,
            'worker': activity.assigned_worker,
            'priority_label': activity.get_priority_display(),
            'date_label': _date_label(activity.scheduled_date),
            'status_key': variant,
            'status_label': activity.get_status_display(),
            'completed_label': _completed_label(activity.completed_at),
            'days_label': '',
            'notes': activity.remarks or '',
            'url': reverse('activities:activity_list'),
        },
    )


def _event_sort_key(event):
    kind_order = {
        'harvest_recorded': 0,
        'harvest_expected': 1,
        'activity': 2,
    }
    return (
        event['start'],
        kind_order.get(event['extendedProps'].get('kind'), 3),
        event['title'].lower(),
    )


def build_calendar_context(user, filters):
    """Aggregate harvest dates and activities into calendar events and cards."""
    farm_id = filters.get('farm_id')
    crop_id = filters.get('crop_id')
    source = filters.get('source', SOURCE_ALL)
    if source not in SOURCE_KEYS:
        source = SOURCE_ALL

    crops_qs = Crop.objects.filter(user=user).select_related('farm')
    harvests_qs = Harvest.objects.filter(user=user).select_related('farm', 'crop')
    activities_qs = FarmActivity.objects.filter(user=user).select_related(
        'farm', 'crop'
    )

    if farm_id:
        crops_qs = crops_qs.filter(farm_id=farm_id)
        harvests_qs = harvests_qs.filter(farm_id=farm_id)
        activities_qs = activities_qs.filter(farm_id=farm_id)

    if crop_id:
        crops_qs = crops_qs.filter(pk=crop_id)
        harvests_qs = harvests_qs.filter(crop_id=crop_id)
        activities_qs = activities_qs.filter(crop_id=crop_id)

    if source == SOURCE_HARVESTS:
        activities_qs = activities_qs.none()
    elif source == SOURCE_ACTIVITIES:
        crops_qs = crops_qs.none()
        harvests_qs = harvests_qs.none()

    crops = list(crops_qs.order_by('expected_harvest_date', 'name', 'pk'))
    harvests = list(harvests_qs.order_by('harvest_date', 'harvest_code', 'pk'))
    activities = list(activities_qs.order_by('scheduled_date', 'pk'))

    events = []
    harvested_crop_ids = {
        harvest.crop_id for harvest in harvests if harvest.crop_id
    }

    for harvest in harvests:
        events.append(_harvest_event(harvest))

    for crop in crops:
        if crop.status == Crop.Status.FAILED:
            continue
        is_harvested = bool(crop.actual_harvest_date) or (
            crop.status == Crop.Status.HARVESTED
        )
        if is_harvested:
            # A harvest record already represents this crop on the calendar.
            if crop.pk in harvested_crop_ids:
                continue
            event = _crop_event(crop, recorded=True)
        else:
            event = _crop_event(crop)
        if event:
            events.append(event)

    for activity in activities:
        events.append(_activity_event(activity))

    events.sort(key=_event_sort_key)

    today = timezone.localdate()
    harvest_cutoff = today + timedelta(days=HARVEST_WINDOW_DAYS)
    active_crops = [
        crop
        for crop in crops
        if crop.status != Crop.Status.FAILED and not crop.actual_harvest_date
    ]
    upcoming_harvest_crops = [
        crop
        for crop in active_crops
        if crop.expected_harvest_date
        and crop.expected_harvest_date <= harvest_cutoff
    ]
    ready_crops = [
        crop for crop in active_crops if crop.maturity_status == 'ready'
    ]
    active_activities = [
        activity for activity in activities if activity.is_active
    ]
    completed_activities = [
        activity
        for activity in activities
        if activity.status == FarmActivity.Status.COMPLETED
    ]

    upcoming_harvests = sorted(
        active_crops,
        key=lambda crop: (
            crop.expected_harvest_date or today,
            crop.name.lower(),
            crop.pk,
        ),
    )[:AGENDA_LIMIT]
    upcoming_activities = sorted(
        active_activities,
        key=lambda activity: (activity.scheduled_date, activity.pk),
    )[:AGENDA_LIMIT]

    recorded_harvest_count = sum(
        1
        for event in events
        if event['extendedProps'].get('kind') == 'harvest_recorded'
    )

    return {
        'calendar_events': events,
        'calendar_summary': {
            'upcoming_harvests': len(upcoming_harvest_crops),
            'ready_harvests': len(ready_crops),
            'recorded_harvests': recorded_harvest_count,
            'active_activities': len(active_activities),
            'completed_activities': len(completed_activities),
            'total_events': len(events),
        },
        'upcoming_harvests': upcoming_harvests,
        'upcoming_activities': upcoming_activities,
        'calendar_legend': legend_for(source),
    }
