"""Shared farm activity scheduling helpers."""

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from .models import FarmActivity


def get_activities(user):
    """Return the user's activities with unfinished work listed first."""
    status_order = Case(
        When(status__in=FarmActivity.STATUS_ACTIVE, then=Value(0)),
        When(status=FarmActivity.Status.COMPLETED, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    return (
        FarmActivity.objects.filter(user=user)
        .select_related('farm', 'crop')
        .annotate(status_order=status_order)
        .order_by('status_order', 'scheduled_date', 'id')
    )


def get_attention_activities(user, limit=8):
    """Return overdue and due-today activities, soonest date first."""
    return (
        FarmActivity.objects.filter(
            user=user,
            status__in=FarmActivity.STATUS_ACTIVE,
            scheduled_date__lte=timezone.localdate(),
        )
        .select_related('farm', 'crop')
        .order_by('scheduled_date', 'id')[:limit]
    )


def get_activity_notifications(user):
    """Return activity notification data for pending, in-progress, and completed counts.

    Returns a dict with counts and brief info for each status category
    to support toast notifications on the activity page.
    """

    # Count activities by status
    pending_count = FarmActivity.objects.filter(
        user=user, status=FarmActivity.Status.PENDING
    ).count()

    in_progress_count = FarmActivity.objects.filter(
        user=user, status=FarmActivity.Status.IN_PROGRESS
    ).count()

    completed_count = FarmActivity.objects.filter(
        user=user, status=FarmActivity.Status.COMPLETED
    ).count()

    # Get a few recent pending activities for notification context
    recent_pending = (
        FarmActivity.objects.filter(user=user, status=FarmActivity.Status.PENDING)
        .select_related('farm', 'crop')
        .order_by('-scheduled_date', '-id')[:3]
    )

    recent_in_progress = (
        FarmActivity.objects.filter(
            user=user, status=FarmActivity.Status.IN_PROGRESS
        )
        .select_related('farm', 'crop')
        .order_by('-scheduled_date', '-id')[:3]
    )

    # Get a few recently completed activities
    recent_completed = (
        FarmActivity.objects.filter(user=user, status=FarmActivity.Status.COMPLETED)
        .select_related('farm', 'crop')
        .order_by('-completed_at', '-id')[:3]
    )

    return {
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'recent_pending': recent_pending,
        'recent_in_progress': recent_in_progress,
        'recent_completed': recent_completed,
    }


def get_activity_notification_items(user, per_status=1):
    """Build notification-bell entries for pending, in-progress, and completed work.

    Each status gets one entry (by default) showing the total count and the
    most recent matching activity. The entries are live summaries derived from
    the farm activity table, so they always reflect the current workflow.
    """
    from django.urls import reverse

    status_meta = (
        {
            'status': FarmActivity.Status.PENDING,
            'title': 'Farm activity pending',
            'badge': 'Pending',
            'tone': 'schedule',
            'icon': 'fas fa-hourglass-half',
            'order': '-updated_at',
        },
        {
            'status': FarmActivity.Status.IN_PROGRESS,
            'title': 'Farm activity in progress',
            'badge': 'In Progress',
            'tone': 'info',
            'icon': 'fas fa-person-digging',
            'order': '-started_at',
        },
        {
            'status': FarmActivity.Status.COMPLETED,
            'title': 'Farm activity completed',
            'badge': 'Completed',
            'tone': 'success',
            'icon': 'fas fa-circle-check',
            'order': '-completed_at',
        },
    )

    activity_url = reverse('activities:activity_list')
    items = []

    for meta in status_meta:
        status = meta['status']
        queryset = FarmActivity.objects.filter(
            user=user, status=status
        ).select_related('farm', 'crop')
        count = queryset.count()
        if not count:
            continue

        recent = list(
            queryset.order_by(meta['order'], '-updated_at', '-id')[:per_status]
        )
        for activity in recent:
            activity_label = activity.get_activity_type_display()
            farm_name = activity.farm.name if activity.farm else ''
            meta_parts = [farm_name]
            if activity.crop:
                meta_parts.append(activity.crop.name.title())
            item_meta = ' · '.join(part for part in meta_parts if part)

            if status == FarmActivity.Status.PENDING:
                noun = 'activity' if count == 1 else 'activities'
                description = (
                    f'{count} {noun} pending. Latest: {activity_label} at '
                    f'{activity.location} on '
                    f'{activity.scheduled_date:%b %d, %Y}.'
                )
                timestamp = activity.updated_at or activity.created_at
            elif status == FarmActivity.Status.IN_PROGRESS:
                noun = 'activity' if count == 1 else 'activities'
                started_on = (
                    activity.started_at
                    or activity.updated_at
                    or activity.created_at
                )
                description = (
                    f'{count} {noun} in progress. Latest: {activity_label} at '
                    f'{activity.location} started '
                    f'{started_on:%b %d, %Y}.'
                )
                timestamp = started_on
            else:
                noun = 'activity' if count == 1 else 'activities'
                completed_on = (
                    activity.completed_at or activity.updated_at or activity.created_at
                )
                description = (
                    f'{count} {noun} completed. Latest: {activity_label} at '
                    f'{activity.location} finished '
                    f'{completed_on:%b %d, %Y}.'
                )
                timestamp = completed_on

            items.append({
                'id': None,
                'title': meta['title'],
                'badge': meta['badge'],
                'description': description,
                'meta': item_meta,
                'timestamp': timestamp,
                'icon': meta['icon'],
                'tone': meta['tone'],
                'url': f'{activity_url}?status={status}',
                'is_unread': False,
                'can_mark_read': False,
            })

    return items
