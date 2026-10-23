"""Shared harvest scheduling and maturity helpers."""

from datetime import timedelta

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from apps.crops.models import Crop, HARVEST_UPCOMING_WINDOW_DAYS

from .models import HarvestSchedule


def get_upcoming_harvests(user, window_days=HARVEST_UPCOMING_WINDOW_DAYS):
    """Return crops that are ready, approaching maturity, or due soon.

    Each crop gets an ``active_schedule`` attribute so the page can show
    whether a harvest activity has already been planned for it.
    """
    cutoff = timezone.localdate() + timedelta(days=window_days)
    crops = (
        Crop.objects.filter(user=user, actual_harvest_date__isnull=True)
        .exclude(status__in=[Crop.Status.HARVESTED, Crop.Status.FAILED])
        .filter(
            Q(status=Crop.Status.READY_FOR_HARVEST)
            | Q(expected_harvest_date__lte=cutoff)
        )
        .select_related('farm')
        .order_by('expected_harvest_date', 'name')
    )
    crops = list(crops)
    if not crops:
        return crops

    crop_ids = [crop.id for crop in crops]
    active_schedules = (
        HarvestSchedule.objects.filter(
            user=user,
            crop_id__in=crop_ids,
            status__in=HarvestSchedule.STATUS_ACTIVE,
        )
        .select_related('farm', 'crop')
        .order_by('scheduled_date', 'id')
    )
    schedules_by_crop = {}
    for schedule in active_schedules:
        schedules_by_crop.setdefault(schedule.crop_id, schedule)

    for crop in crops:
        crop.active_schedule = schedules_by_crop.get(crop.id)
    return crops


def get_harvest_schedules(user):
    """Return schedules with active activities listed before finished ones."""
    status_order = Case(
        When(status__in=HarvestSchedule.STATUS_ACTIVE, then=Value(0)),
        When(status=HarvestSchedule.Status.COMPLETED, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    return (
        HarvestSchedule.objects.filter(user=user)
        .select_related('farm', 'crop', 'harvest_record')
        .annotate(status_order=status_order)
        .order_by('status_order', 'scheduled_date', 'id')
    )
