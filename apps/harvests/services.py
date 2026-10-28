"""Crop-driven harvest readiness and notification helpers.

The crop is the single source of truth for harvests. A harvest date is
calculated from the planting date and the crop's days to maturity, and the
system creates an in-app notification as soon as a crop becomes ready.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.crops.models import (
    Crop,
    HARVEST_APPROACHING_DAYS,
    HARVEST_UPCOMING_WINDOW_DAYS,
)

from .models import HarvestNotification


ACTIVE_CROP_STATUSES = (
    Crop.Status.PLANTING,
    Crop.Status.GROWING,
    Crop.Status.MATURING,
)

SYSTEM_MANAGED_STATUSES = ACTIVE_CROP_STATUSES + (Crop.Status.READY_FOR_HARVEST,)


def active_crops(user):
    """Return crops that still need to be harvested."""
    return (
        Crop.objects.filter(user=user, actual_harvest_date__isnull=True)
        .exclude(status__in=[Crop.Status.HARVESTED, Crop.Status.FAILED])
        .select_related('farm')
        .order_by('expected_harvest_date', 'name')
    )


def _read_notifications(crop, kinds=None, expected_date=None):
    """Mark the crop's unread notifications as read."""
    queryset = HarvestNotification.objects.filter(crop=crop, is_read=False)
    if kinds:
        queryset = queryset.filter(kind__in=kinds)
    if expected_date:
        queryset = queryset.filter(expected_harvest_date=expected_date)
    return queryset.update(is_read=True, read_at=timezone.now())


def _notification_message(crop, kind, days):
    if kind == HarvestNotification.Kind.READY:
        return (
            f'{crop.name} on {crop.farm.name} is ready for harvest. '
            f'The system assigned {crop.expected_harvest_date:%b %d, %Y} as the harvest date.'
        )
    if days == 0:
        countdown = 'today'
    elif days == 1:
        countdown = 'tomorrow'
    else:
        countdown = f'in {days} days'
    return (
        f'{crop.name} on {crop.farm.name} will be ready for harvest {countdown} '
        f'({crop.expected_harvest_date:%b %d, %Y}).'
    )


def _create_notification(crop, kind, days):
    if not crop.user_id:
        return None, False
    notification, created = HarvestNotification.objects.get_or_create(
        crop=crop,
        kind=kind,
        expected_harvest_date=crop.expected_harvest_date,
        defaults={
            'user': crop.user,
            'message': _notification_message(crop, kind, days),
        },
    )
    return notification, created


def _sync_crop_status(crop, days_to_harvest, today):
    """Move a crop through its natural stages automatically."""
    if crop.status not in SYSTEM_MANAGED_STATUSES:
        return False

    if days_to_harvest <= 0:
        new_status = Crop.Status.READY_FOR_HARVEST
    elif days_to_harvest <= HARVEST_APPROACHING_DAYS:
        new_status = Crop.Status.MATURING
    elif crop.status == Crop.Status.READY_FOR_HARVEST or (
        crop.planting_date and (today - crop.planting_date).days > 7
    ):
        # Editing the planting date or maturity estimate can push a crop's
        # assigned date back into the future; drop it out of "ready".
        new_status = Crop.Status.GROWING
    else:
        return False

    if crop.status == new_status:
        return False

    crop.status = new_status
    crop.save(update_fields=['status', 'updated_at'])
    return True


def evaluate_crop(crop, today=None, notify=True):
    """Update one crop's readiness and create/close its notifications.

    Returns a small dictionary describing the result so views can show an
    immediate confirmation after a crop is added or edited.
    """
    today = today or timezone.localdate()

    if not crop.expected_harvest_date and crop.planting_date:
        crop.expected_harvest_date = crop.calculate_expected_harvest_date()
        crop.save(update_fields=['expected_harvest_date', 'updated_at'])

    result = {
        'status': 'upcoming',
        'days_to_harvest': crop.days_to_harvest,
        'notification': None,
        'notification_created': False,
        'status_changed': False,
    }

    if crop.actual_harvest_date or crop.status in (
        Crop.Status.HARVESTED,
        Crop.Status.FAILED,
    ):
        _read_notifications(crop)
        result['status'] = 'resolved'
        return result

    days = crop.days_to_harvest
    if days is None:
        return result

    result['days_to_harvest'] = days
    result['status_changed'] = _sync_crop_status(crop, days, today)

    # A notification for a previously calculated harvest date is stale when
    # the planting date or days to maturity change.
    HarvestNotification.objects.filter(crop=crop, is_read=False).exclude(
        expected_harvest_date=crop.expected_harvest_date
    ).update(is_read=True, read_at=timezone.now())

    is_due = days <= 0 or crop.status == Crop.Status.READY_FOR_HARVEST
    if is_due:
        # The approaching reminder is no longer useful once the crop is ready.
        _read_notifications(crop, kinds=[HarvestNotification.Kind.APPROACHING])
        result['status'] = 'ready'
        if notify:
            notification, created = _create_notification(
                crop, HarvestNotification.Kind.READY, days
            )
            result['notification'] = notification
            result['notification_created'] = created
        return result

    if days <= HARVEST_APPROACHING_DAYS:
        result['status'] = 'approaching'
        if notify:
            notification, created = _create_notification(
                crop, HarvestNotification.Kind.APPROACHING, days
            )
            result['notification'] = notification
            result['notification_created'] = created
    return result


def sync_harvest_readiness(user, notify=True):
    """Refresh readiness for every active crop owned by a user."""
    today = timezone.localdate()
    summary = {
        'ready': 0,
        'approaching': 0,
        'notifications_created': 0,
        'crops': [],
    }
    for crop in active_crops(user):
        result = evaluate_crop(crop, today=today, notify=notify)
        summary['crops'].append((crop, result))
        if result['status'] == 'ready':
            summary['ready'] += 1
        elif result['status'] == 'approaching':
            summary['approaching'] += 1
        if result['notification_created']:
            summary['notifications_created'] += 1
    return summary


def get_harvest_board(user):
    """Return ready, approaching, and upcoming crops for the harvest page."""
    sync_harvest_readiness(user)
    today = timezone.localdate()
    cutoff = today + timedelta(days=HARVEST_UPCOMING_WINDOW_DAYS)

    crops = list(active_crops(user))
    ready_crops = []
    approaching_crops = []
    upcoming_crops = []
    for crop in crops:
        status = crop.maturity_status
        if status == 'ready':
            ready_crops.append(crop)
        elif status == 'approaching':
            approaching_crops.append(crop)
        elif crop.expected_harvest_date and crop.expected_harvest_date <= cutoff:
            upcoming_crops.append(crop)

    ready_crops.sort(key=lambda crop: (crop.expected_harvest_date, crop.name))
    approaching_crops.sort(key=lambda crop: (crop.expected_harvest_date, crop.name))
    upcoming_crops.sort(key=lambda crop: (crop.expected_harvest_date, crop.name))

    return {
        'crops': crops,
        'ready_crops': ready_crops,
        'approaching_crops': approaching_crops,
        'upcoming_crops': upcoming_crops,
        'ready_count': len(ready_crops),
        'approaching_count': len(approaching_crops),
        'upcoming_count': len(ready_crops) + len(approaching_crops) + len(upcoming_crops),
    }


def get_upcoming_harvests(user, window_days=HARVEST_UPCOMING_WINDOW_DAYS):
    """Return ready and soon-to-be-ready crops (dashboard compatibility)."""
    board = get_harvest_board(user)
    cutoff = timezone.localdate() + timedelta(days=window_days)
    crops = [
        crop for crop in board['crops']
        if crop.maturity_status == 'ready'
        or (
            crop.expected_harvest_date
            and crop.expected_harvest_date <= cutoff
        )
    ]
    return crops


def get_notifications(user, unread_only=False, limit=20):
    """Return the user's harvest notifications, newest first."""
    queryset = HarvestNotification.objects.filter(user=user).select_related(
        'crop', 'crop__farm'
    )
    if unread_only:
        queryset = queryset.filter(is_read=False)
    if limit:
        queryset = queryset[:limit]
    return list(queryset)


def get_unread_notification_count(user):
    return HarvestNotification.objects.filter(user=user, is_read=False).count()


def get_ready_crop_count(user):
    return active_crops(user).filter(
        Q(status=Crop.Status.READY_FOR_HARVEST)
        | Q(expected_harvest_date__lte=timezone.localdate())
    ).count()


def mark_all_notifications_read(user):
    return HarvestNotification.objects.filter(user=user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )


def resolve_crop_notifications(crop):
    """Close every unread notification when a crop is harvested or fails."""
    return _read_notifications(crop)


def reopen_crop_notifications(crop):
    """Reopen the readiness alert when a harvest record is deleted."""
    if not crop.expected_harvest_date:
        return 0
    return HarvestNotification.objects.filter(
        crop=crop,
        kind=HarvestNotification.Kind.READY,
        expected_harvest_date=crop.expected_harvest_date,
    ).update(is_read=False, read_at=None)
