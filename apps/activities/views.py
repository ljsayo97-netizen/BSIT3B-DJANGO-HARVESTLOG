"""Farm activity scheduling views (page + AJAX endpoints)."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.crops.models import Crop
from apps.farms.models import Farm

from .models import FarmActivity
from .services import get_activities, get_attention_activities


ACTIVITY_SORT_FIELDS = {
    'scheduled_date': 'scheduled_date',
    '-scheduled_date': '-scheduled_date',
    'priority': 'priority_order',
    '-priority': '-priority_order',
    'status': 'status_order',
    '-status': '-status_order',
    'activity_type': 'activity_type',
    '-activity_type': '-activity_type',
    'farm': 'farm__name',
    '-farm': '-farm__name',
    'worker': 'assigned_worker',
    '-worker': '-assigned_worker',
}


def _base_queryset(user):
    """The user's activities annotated with the orderings used for sorting."""
    priority_order = Case(
        When(priority=FarmActivity.Priority.URGENT, then=Value(0)),
        When(priority=FarmActivity.Priority.HIGH, then=Value(1)),
        When(priority=FarmActivity.Priority.MEDIUM, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    return get_activities(user).annotate(priority_order=priority_order)


def _filter_activities(request):
    """Apply the shared search, filter, and sort options to the queryset."""
    queryset = _base_queryset(request.user)

    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    priority = request.GET.get('priority', '').strip()
    activity_type = request.GET.get('type', '').strip()
    farm_id = request.GET.get('farm', '').strip()
    date_from_raw = request.GET.get('date_from', '').strip()
    date_to_raw = request.GET.get('date_to', '').strip()
    sort = request.GET.get('sort', 'scheduled_date').strip()

    if query:
        queryset = queryset.filter(
            Q(location__icontains=query) |
            Q(assigned_worker__icontains=query) |
            Q(remarks__icontains=query) |
            Q(activity_type__icontains=query) |
            Q(farm__name__icontains=query) |
            Q(crop__name__icontains=query)
        )

    valid_statuses = dict(FarmActivity.Status.choices)
    if status in valid_statuses:
        queryset = queryset.filter(status=status)

    valid_priorities = dict(FarmActivity.Priority.choices)
    if priority in valid_priorities:
        queryset = queryset.filter(priority=priority)

    valid_types = dict(FarmActivity.ActivityType.choices)
    if activity_type in valid_types:
        queryset = queryset.filter(activity_type=activity_type)

    if farm_id:
        try:
            queryset = queryset.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    date_from = parse_date(date_from_raw) if date_from_raw else None
    if date_from:
        queryset = queryset.filter(scheduled_date__gte=date_from)

    date_to = parse_date(date_to_raw) if date_to_raw else None
    if date_to:
        queryset = queryset.filter(scheduled_date__lte=date_to)

    queryset = queryset.order_by(
        ACTIVITY_SORT_FIELDS.get(sort, 'scheduled_date'),
        'id',
    )

    filters = {
        'query': query,
        'status': status,
        'priority': priority,
        'activity_type': activity_type,
        'farm_id': farm_id,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
        'sort': sort,
    }
    return queryset, filters


def _activity_json(activity):
    """Serialize a farm activity to a JSON-friendly dict."""
    return {
        'id': activity.id,
        'activity_type': activity.activity_type,
        'activity_type_display': activity.get_activity_type_display(),
        'farm_id': activity.farm_id,
        'farm_name': activity.farm.name,
        'crop_id': activity.crop_id,
        'crop_name': activity.crop.name if activity.crop else None,
        'location': activity.location,
        'scheduled_date': (
            activity.scheduled_date.isoformat() if activity.scheduled_date else None
        ),
        'assigned_worker': activity.assigned_worker,
        'priority': activity.priority,
        'priority_display': activity.get_priority_display(),
        'status': activity.status,
        'status_display': activity.get_status_display(),
        'remarks': activity.remarks,
        'started_at': activity.started_at.isoformat() if activity.started_at else None,
        'completed_at': activity.completed_at.isoformat() if activity.completed_at else None,
        'days_until': activity.days_until,
        'is_overdue': activity.is_overdue,
        'next_status': activity.next_status,
        'next_status_label': activity.next_status_label,
        'created_at': activity.created_at.isoformat(),
    }


@login_required(login_url='login')
def activity_list_page(request):
    """Render the farm activity scheduling board."""
    activities_list, filters = _filter_activities(request)

    farms = Farm.objects.filter(user=request.user).order_by('name')
    crops = Crop.objects.filter(user=request.user).select_related('farm').order_by('name')

    # Existing locations (from farms and saved activities) offered as
    # suggestions while typing the activity location.
    location_suggestions = sorted({
        *(farm.location.strip() for farm in farms if farm.location and farm.location.strip()),
        *(
            value.strip()
            for value in activities_list.values_list('location', flat=True)
            if value and value.strip()
        ),
    }, key=str.lower)

    today = timezone.localdate()
    summary = activities_list.order_by().aggregate(
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

    paginator = Paginator(activities_list, 10)
    activities = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'activities/list.html', {
        'activities': activities,
        'query_string': params.urlencode(),
        'farms': farms,
        'crops': crops,
        'location_suggestions': location_suggestions,
        'summary': summary,
        'attention_activities': get_attention_activities(request.user),
        'activity_type_choices': FarmActivity.ActivityType.choices,
        'priority_choices': FarmActivity.Priority.choices,
        'status_choices': FarmActivity.Status.choices,
        'sort_choices': [
            ('scheduled_date', 'Scheduled date (soonest first)'),
            ('-scheduled_date', 'Scheduled date (latest first)'),
            ('-priority', 'Priority (urgent first)'),
            ('status', 'Status (unfinished first)'),
            ('activity_type', 'Activity type'),
            ('farm', 'Farm'),
            ('worker', 'Assigned worker'),
        ],
        **filters,
    })


@login_required(login_url='login')
def activity_list_ajax(request):
    """Return the signed-in user's filtered farm activities as JSON."""
    activities_list, _ = _filter_activities(request)

    paginator = Paginator(activities_list, 10)
    page = paginator.get_page(request.GET.get('page', 1))

    return JsonResponse({
        'data': [_activity_json(activity) for activity in page.object_list],
        'has_next': page.has_next(),
        'has_prev': page.has_previous(),
        'page': page.number,
        'pages': page.paginator.num_pages,
        'total': page.paginator.count,
    })


@login_required(login_url='login')
def activity_get_ajax(request, pk):
    """Return one of the signed-in user's farm activities as JSON."""
    activity = get_object_or_404(
        FarmActivity.objects.select_related('farm', 'crop'),
        pk=pk,
        user=request.user,
    )
    return JsonResponse(_activity_json(activity))


@login_required(login_url='login')
@require_POST
def activity_save_ajax(request):
    """Validate and create or update a farm activity, returning its data."""
    activity_id = request.POST.get('id', '').strip()

    if activity_id:
        activity = get_object_or_404(FarmActivity, pk=activity_id, user=request.user)
        is_update = True
    else:
        activity = FarmActivity(user=request.user)
        is_update = False

    activity_type = request.POST.get('activity_type', '').strip()
    farm_id = request.POST.get('farm_id', '').strip()
    crop_id = request.POST.get('crop_id', '').strip()
    location = request.POST.get('location', '').strip()
    scheduled_date_raw = request.POST.get('scheduled_date', '').strip()
    assigned_worker = request.POST.get('assigned_worker', '').strip()
    priority = request.POST.get('priority', '').strip()
    status = request.POST.get('status', '').strip()
    remarks = request.POST.get('remarks', '').strip()

    valid_types = dict(FarmActivity.ActivityType.choices)
    if activity_type not in valid_types:
        return JsonResponse({'error': 'Please select a valid activity type.'}, status=400)

    if not farm_id:
        return JsonResponse({'error': 'Please select a farm.'}, status=400)
    try:
        farm = Farm.objects.get(pk=farm_id, user=request.user)
    except Farm.DoesNotExist:
        return JsonResponse({'error': 'Selected farm does not exist.'}, status=400)

    crop = None
    if crop_id:
        try:
            crop = Crop.objects.get(pk=crop_id, user=request.user)
        except Crop.DoesNotExist:
            return JsonResponse({'error': 'Selected crop does not exist.'}, status=400)

        if crop.farm_id != farm.id:
            return JsonResponse(
                {'error': 'Selected crop belongs to a different farm.'},
                status=400,
            )

    if not location:
        return JsonResponse({'error': 'Location is required.'}, status=400)

    if not scheduled_date_raw:
        return JsonResponse({'error': 'Scheduled date is required.'}, status=400)
    scheduled_date = parse_date(scheduled_date_raw)
    if scheduled_date is None:
        return JsonResponse({'error': 'Enter a valid scheduled date.'}, status=400)

    if not assigned_worker:
        return JsonResponse({'error': 'Please assign a worker to the activity.'}, status=400)

    valid_priorities = dict(FarmActivity.Priority.choices)
    if priority not in valid_priorities:
        return JsonResponse({'error': 'Please select a valid priority.'}, status=400)

    valid_statuses = dict(FarmActivity.Status.choices)
    if status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid status.'}, status=400)

    if not is_update and status != FarmActivity.Status.PENDING:
        return JsonResponse(
            {'error': 'New activities start as Pending. Advance them to In Progress '
                      'and then Completed as the work happens.'},
            status=400,
        )

    if is_update and not activity.can_transition_to(status):
        return JsonResponse(
            {'error': 'Activities follow the Pending -> In Progress -> Completed flow. '
                      'Move this activity to "In Progress" before completing it, or '
                      'reopen it before moving it back to Pending.'},
            status=400,
        )

    activity.farm = farm
    activity.crop = crop
    activity.activity_type = activity_type
    activity.location = location
    activity.scheduled_date = scheduled_date
    activity.assigned_worker = assigned_worker
    activity.priority = priority
    activity.remarks = remarks
    activity.apply_status(status)

    try:
        activity.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save the activity due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'"{activity.get_activity_type_display()}" on {activity.location} has been '
        f'{"updated" if is_update else "scheduled"} successfully.',
    )

    return JsonResponse({'status': 'success', 'activity': _activity_json(activity)})


@login_required(login_url='login')
@require_POST
def activity_status_ajax(request, pk):
    """Move one activity one step along the Pending -> In Progress -> Completed flow."""
    activity = get_object_or_404(FarmActivity, pk=pk, user=request.user)

    requested = request.POST.get('status', '').strip()
    new_status = requested or activity.next_status

    valid_statuses = dict(FarmActivity.Status.choices)
    if new_status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid status.'}, status=400)

    if not activity.can_transition_to(new_status):
        return JsonResponse(
            {'error': 'Activities follow the Pending -> In Progress -> Completed flow.'},
            status=400,
        )

    activity.apply_status(new_status)
    activity.save(update_fields=['status', 'started_at', 'completed_at', 'updated_at'])

    messages.success(
        request,
        f'"{activity.get_activity_type_display()}" on {activity.location} is now '
        f'{activity.get_status_display()}.',
    )

    return JsonResponse({'status': 'success', 'activity': _activity_json(activity)})


@login_required(login_url='login')
@require_POST
def activity_delete_ajax(request, pk):
    """Delete one of the signed-in user's farm activities."""
    activity = get_object_or_404(FarmActivity, pk=pk, user=request.user)
    description = str(activity)
    activity.delete()

    messages.success(request, f'Activity "{description}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Activity "{description}" has been deleted successfully.',
    })


@login_required(login_url='login')
def activity_export(request):
    """Export the filtered farm activities as a CSV file."""
    activities_list, _ = _filter_activities(request)

    response = HttpResponse(content_type='text/csv')
    filename = f'farm_activities_{timezone.localdate():%Y%m%d}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Activity ID',
        'Scheduled Date',
        'Activity Type',
        'Farm',
        'Location',
        'Crop',
        'Assigned Worker',
        'Priority',
        'Status',
        'Started At',
        'Completed At',
        'Remarks',
    ])

    for activity in activities_list.iterator():
        writer.writerow([
            activity.pk,
            activity.scheduled_date.isoformat() if activity.scheduled_date else '',
            activity.get_activity_type_display(),
            activity.farm.name,
            activity.location,
            activity.crop.name if activity.crop else '',
            activity.assigned_worker,
            activity.get_priority_display(),
            activity.get_status_display(),
            activity.started_at.isoformat() if activity.started_at else '',
            activity.completed_at.isoformat() if activity.completed_at else '',
            activity.remarks,
        ])

    return response
