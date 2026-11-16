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
