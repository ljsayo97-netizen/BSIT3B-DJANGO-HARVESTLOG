"""Harvest scheduling, recording, and history views."""

import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.crops.models import Crop
from apps.farms.models import Farm

from .models import Harvest, HarvestSchedule
from .services import get_harvest_schedules, get_upcoming_harvests


def _parse_decimal(raw_value):
    """Convert a value to a decimal, returning None when invalid."""
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def _parse_int(raw_value):
    """Convert a value to an integer, returning None when invalid."""
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


HARVEST_SORT_FIELDS = {
    'harvest_code': 'harvest_code',
    '-harvest_code': '-harvest_code',
    'harvest_date': 'harvest_date',
    '-harvest_date': '-harvest_date',
    'crop_type': 'crop_type',
    '-crop_type': '-crop_type',
    'farm': 'farm__name',
    '-farm': '-farm__name',
    'quantity': 'quantity_harvested',
    '-quantity': '-quantity_harvested',
    'workers': 'workers_count',
    '-workers': '-workers_count',
}


def _filter_harvests(request, queryset=None):
    """Apply shared search, filter, and sort options to a harvest queryset."""
    if queryset is None:
        queryset = Harvest.objects.filter(user=request.user).select_related('farm', 'crop')

    query = request.GET.get('q', '').strip()
    quality = request.GET.get('quality', '').strip()
    farm_id = request.GET.get('farm', '').strip()
    crop_id = request.GET.get('crop', '').strip()
    date_from_raw = request.GET.get('date_from', '').strip()
    date_to_raw = request.GET.get('date_to', '').strip()
    sort = request.GET.get('sort', '-harvest_date').strip()

    if query:
        queryset = queryset.filter(
            Q(harvest_code__icontains=query) |
            Q(crop_type__icontains=query) |
            Q(location__icontains=query) |
            Q(harvested_by__icontains=query) |
            Q(supervised_by__icontains=query) |
            Q(notes__icontains=query) |
            Q(farm__name__icontains=query) |
            Q(crop__name__icontains=query)
        )

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality in valid_grades:
        queryset = queryset.filter(quality_grade=quality)

    if farm_id:
        try:
            queryset = queryset.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    if crop_id:
        try:
            queryset = queryset.filter(crop_id=int(crop_id))
        except ValueError:
            pass

    date_from = parse_date(date_from_raw) if date_from_raw else None
    if date_from:
        queryset = queryset.filter(harvest_date__gte=date_from)

    date_to = parse_date(date_to_raw) if date_to_raw else None
    if date_to:
        queryset = queryset.filter(harvest_date__lte=date_to)

    order_by = HARVEST_SORT_FIELDS.get(sort, '-harvest_date')
    queryset = queryset.order_by(order_by)

    filters = {
        'query': query,
        'quality': quality,
        'farm_id': farm_id,
        'crop_id': crop_id,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
        'sort': sort,
        'current_sort': sort,
    }
    return queryset, filters


def _month_starts(count=12):
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


def _csv_value(value):
    """Render a value safely for spreadsheet applications."""
    text = '' if value is None else str(value)
    if text.startswith(('=', '+', '-', '@')):
        return f"'{text}"
    return text


def _schedule_harvest_record(schedule):
    """Return the harvest recorded against a schedule, if one exists."""
    try:
        return schedule.harvest_record
    except ObjectDoesNotExist:
        return None


def _harvest_json(harvest):
    """Serialize a harvest instance to a JSON-friendly dict."""
    return {
        'id': harvest.id,
        'harvest_code': harvest.harvest_code,
        'farm_id': harvest.farm_id,
        'farm_name': harvest.farm.name,
        'crop_id': harvest.crop_id,
        'crop_name': harvest.crop.name if harvest.crop else None,
        'schedule_id': harvest.schedule_id,
        'harvest_date': harvest.harvest_date.isoformat() if harvest.harvest_date else None,
        'location': harvest.location,
        'crop_type': harvest.crop_type,
        'quantity_harvested': float(harvest.quantity_harvested),
        'unit': harvest.unit,
        'quality_grade': harvest.quality_grade,
        'quality_grade_display': harvest.get_quality_grade_display(),
        'workers_count': harvest.workers_count,
        'harvested_by': harvest.harvested_by,
        'supervised_by': harvest.supervised_by,
        'notes': harvest.notes,
        'created_at': harvest.created_at.isoformat(),
    }


def _schedule_json(schedule):
    """Serialize a harvest schedule to a JSON-friendly dict."""
    record = _schedule_harvest_record(schedule)
    return {
        'id': schedule.id,
        'farm_id': schedule.farm_id,
        'farm_name': schedule.farm.name,
        'crop_id': schedule.crop_id,
        'crop_name': schedule.crop.name if schedule.crop else None,
        'field_name': schedule.field_name,
        'scheduled_date': schedule.scheduled_date.isoformat() if schedule.scheduled_date else None,
        'expected_quantity': (
            float(schedule.expected_quantity)
            if schedule.expected_quantity is not None
            else None
        ),
        'unit': schedule.unit,
        'workers_count': schedule.workers_count,
        'assigned_to': schedule.assigned_to,
        'supervisor': schedule.supervisor,
        'status': schedule.status,
        'status_display': schedule.get_status_display(),
        'notes': schedule.notes,
        'days_until': schedule.days_until,
        'is_active': schedule.is_active,
        'harvest_record_id': record.id if record else None,
        'harvest_code': record.harvest_code if record else None,
    }


@login_required(login_url='login')
def harvest_list_page(request):
    """Render harvest scheduling, upcoming harvests, and harvest history."""
    harvests_list, filters = _filter_harvests(request)

    farms = Farm.objects.filter(user=request.user).order_by('name')
    crops = Crop.objects.filter(user=request.user).select_related('farm').order_by('name')

    paginator = Paginator(harvests_list, 10)
    page_number = request.GET.get('page', 1)
    harvests = paginator.get_page(page_number)

    upcoming_harvests = get_upcoming_harvests(request.user)
    schedules = list(get_harvest_schedules(request.user))
    active_schedules = [schedule for schedule in schedules if schedule.is_active]
    all_harvests = Harvest.objects.filter(user=request.user)
    total_harvests = all_harvests.count()
    total_quantity = all_harvests.aggregate(total=Sum('quantity_harvested'))['total'] or 0

    return render(request, 'harvests/list.html', {
        'harvests': harvests,
        'farms': farms,
        'crops': crops,
        'upcoming_harvests': upcoming_harvests,
        'schedules': schedules,
        'active_schedule_count': len(active_schedules),
        'total_harvests': total_harvests,
        'total_quantity': total_quantity,
        'quality_choices': Harvest.QualityGrade.choices,
        'schedule_status_choices': HarvestSchedule.Status.choices,
        **filters,
    })


@login_required(login_url='login')
def harvest_list_ajax(request):
    """Return the signed-in user's filtered/sorted harvests as paginated JSON."""
    harvests_list, _ = _filter_harvests(request)

    paginator = Paginator(harvests_list, 10)
    page_number = request.GET.get('page', 1)
    harvests = paginator.get_page(page_number)

    return JsonResponse({
        'data': [_harvest_json(harvest) for harvest in harvests.object_list],
        'has_next': harvests.has_next(),
        'has_prev': harvests.has_previous(),
        'page': harvests.number,
        'pages': harvests.paginator.num_pages,
        'total': harvests.paginator.count,
    })


@login_required(login_url='login')
def harvest_history_page(request):
    """Render a filterable monitoring view of the user's harvest history."""
    harvests_list, filters = _filter_harvests(request)
    base = harvests_list.order_by()

    summary = base.aggregate(
        total_harvests=Count('id'),
        total_workers=Sum('workers_count'),
        total_quantity=Sum('quantity_harvested'),
        farm_count=Count('farm', distinct=True),
    )
    summary['total_workers'] = summary['total_workers'] or 0
    summary['total_quantity'] = summary['total_quantity'] or 0
    total_records = summary['total_harvests']

    unit_totals = list(
        base.values('unit')
        .annotate(records=Count('id'), total=Sum('quantity_harvested'))
        .order_by('-total', 'unit')
    )

    month_starts = _month_starts()
    monthly_rows = (
        base.filter(harvest_date__gte=month_starts[0])
        .annotate(month=TruncMonth('harvest_date'))
        .values('month')
        .annotate(records=Count('id'))
        .order_by('month')
    )
    monthly_map = {
        row['month'].strftime('%Y-%m'): row['records']
        for row in monthly_rows
        if row['month']
    }
    monthly_labels = [month.strftime('%b %Y') for month in month_starts]
    monthly_counts = [
        monthly_map.get(month.strftime('%Y-%m'), 0) for month in month_starts
    ]

    farm_rows = list(
        base.values('farm__name')
        .annotate(
            records=Count('id'),
            workers=Sum('workers_count'),
            quantity=Sum('quantity_harvested'),
        )
        .order_by('-records', 'farm__name')[:8]
    )

    crop_rows = list(
        base.values('crop_type')
        .annotate(
            records=Count('id'),
            workers=Sum('workers_count'),
            quantity=Sum('quantity_harvested'),
        )
        .order_by('-records', 'crop_type')[:8]
    )

    quality_labels = dict(Harvest.QualityGrade.choices)
    quality_rows = list(
        base.values('quality_grade')
        .annotate(records=Count('id'))
        .order_by('-records')
    )
    for row in quality_rows:
        row['label'] = quality_labels.get(row['quality_grade'], row['quality_grade'])
        row['percent'] = (
            round(row['records'] * 100 / total_records) if total_records else 0
        )

    paginator = Paginator(harvests_list, 20)
    harvests = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'harvests/history.html', {
        'harvests': harvests,
        'farms': Farm.objects.filter(user=request.user).order_by('name'),
        'crops': Crop.objects.filter(user=request.user).select_related('farm').order_by('name'),
        'quality_choices': Harvest.QualityGrade.choices,
        'summary': summary,
        'unit_totals': unit_totals,
        'monthly_labels': monthly_labels,
        'monthly_counts': monthly_counts,
        'farm_rows': farm_rows,
        'crop_rows': crop_rows,
        'quality_rows': quality_rows,
        'query_string': params.urlencode(),
        **filters,
    })


@login_required(login_url='login')
def harvest_history_export(request):
    """Export the filtered harvest history as a CSV file."""
    harvests_list, _ = _filter_harvests(request)

    response = HttpResponse(content_type='text/csv')
    filename = f'harvest_history_{timezone.localdate():%Y%m%d}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Harvest ID',
        'Harvest Date',
        'Farm',
        'Field',
        'Crop',
        'Crop Type',
        'Quantity',
        'Unit',
        'Quality',
        'Workers',
        'Team Lead',
        'Supervisor',
        'Scheduled Harvest',
        'Remarks',
    ])

    records = harvests_list.select_related('farm', 'crop', 'schedule')
    for harvest in records.iterator():
        writer.writerow([
            _csv_value(harvest.harvest_code),
            harvest.harvest_date.isoformat() if harvest.harvest_date else '',
            _csv_value(harvest.farm.name),
            _csv_value(harvest.location),
            _csv_value(harvest.crop.name if harvest.crop else ''),
            _csv_value(harvest.crop_type),
            harvest.quantity_harvested,
            _csv_value(harvest.unit),
            _csv_value(harvest.get_quality_grade_display()),
            harvest.workers_count,
            _csv_value(harvest.harvested_by),
            _csv_value(harvest.supervised_by),
            'Yes' if harvest.schedule_id else 'No',
            _csv_value(harvest.notes),
        ])

    return response


@login_required(login_url='login')
def harvest_get_ajax(request, pk):
    """Return one of the signed-in user's harvest records as JSON."""
    harvest = get_object_or_404(
        Harvest.objects.select_related('farm', 'crop', 'schedule'),
        pk=pk,
        user=request.user,
    )
    return JsonResponse(_harvest_json(harvest))


@login_required(login_url='login')
@require_POST
def harvest_save_ajax(request):
    """Validate and create or update a harvest record, returning its data as JSON."""
    harvest_id = request.POST.get('id', '').strip()
    schedule_id = request.POST.get('schedule_id', '').strip()

    if harvest_id:
        harvest = get_object_or_404(Harvest, pk=harvest_id, user=request.user)
        is_update = True
    else:
        harvest = Harvest(user=request.user)
        is_update = False

    previous_crop = harvest.crop if is_update else None
    previous_schedule = harvest.schedule if is_update else None

    schedule = None
    if schedule_id:
        try:
            schedule = HarvestSchedule.objects.select_related('farm', 'crop').get(
                pk=schedule_id,
                user=request.user,
            )
        except HarvestSchedule.DoesNotExist:
            return JsonResponse({'error': 'Selected harvest schedule does not exist.'}, status=400)

        if schedule.status == HarvestSchedule.Status.CANCELLED:
            return JsonResponse(
                {'error': 'This harvest schedule was cancelled and can no longer be recorded.'},
                status=400,
            )

        linked_record = _schedule_harvest_record(schedule)
        if linked_record and linked_record.pk != harvest.pk:
            return JsonResponse(
                {'error': f'Harvest {linked_record.harvest_code} has already been recorded for this schedule.'},
                status=400,
            )

    farm_id = request.POST.get('farm_id', '').strip()
    crop_id = request.POST.get('crop_id', '').strip()
    harvest_date_raw = request.POST.get('harvest_date', '').strip()
    location = request.POST.get('location', '').strip()
    crop_type = request.POST.get('crop_type', '').strip()
    quantity_raw = request.POST.get('quantity_harvested', '').strip()
    unit = request.POST.get('unit', '').strip()
    quality_grade = request.POST.get('quality_grade', '').strip()
    workers_raw = request.POST.get('workers_count', '').strip()
    harvested_by = request.POST.get('harvested_by', '').strip()
    supervised_by = request.POST.get('supervised_by', '').strip()
    notes = request.POST.get('notes', '').strip()

    # Fall back to the linked schedule's details so a schedule can be
    # recorded with as little typing as possible.
    if schedule:
        farm_id = farm_id or str(schedule.farm_id)
        crop_id = crop_id or (str(schedule.crop_id) if schedule.crop_id else '')
        location = location or schedule.field_name
        crop_type = crop_type or (schedule.crop.name if schedule.crop else '')
        workers_raw = workers_raw or str(schedule.workers_count)
        harvested_by = harvested_by or schedule.assigned_to or schedule.supervisor
        supervised_by = supervised_by or schedule.supervisor

    if not farm_id:
        return JsonResponse({'error': 'Please select a farm.'}, status=400)
    try:
        farm = Farm.objects.get(pk=farm_id, user=request.user)
    except Farm.DoesNotExist:
        return JsonResponse({'error': 'Selected farm does not exist.'}, status=400)

    if schedule and schedule.farm_id != farm.id:
        return JsonResponse(
            {'error': 'The selected farm does not match the harvest schedule.'},
            status=400,
        )

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

        if schedule and schedule.crop_id and schedule.crop_id != crop.id:
            return JsonResponse(
                {'error': 'The selected crop does not match the harvest schedule.'},
                status=400,
            )

    if not harvest_date_raw:
        return JsonResponse({'error': 'Harvest date is required.'}, status=400)
    harvest_date = parse_date(harvest_date_raw)
    if harvest_date is None:
        return JsonResponse({'error': 'Enter a valid harvest date.'}, status=400)

    if not location:
        return JsonResponse({'error': 'Field / harvest location is required.'}, status=400)
    if not crop_type:
        return JsonResponse({'error': 'Crop type is required.'}, status=400)

    quantity_value = _parse_decimal(quantity_raw)
    if quantity_value is None or quantity_value < 0:
        return JsonResponse(
            {'error': 'Quantity must be a valid number (0 or greater).'},
            status=400,
        )

    workers_count = _parse_int(workers_raw) if workers_raw else 0
    if workers_count is None or workers_count < 0:
        return JsonResponse(
            {'error': 'Workers must be a valid number (0 or greater).'},
            status=400,
        )

    if not unit:
        unit = 'kg'

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality_grade not in valid_grades:
        return JsonResponse({'error': 'Please select a valid quality grade.'}, status=400)

    if not harvested_by:
        return JsonResponse({'error': 'Harvest team lead is required.'}, status=400)

    harvest.farm = farm
    harvest.crop = crop
    harvest.schedule = schedule
    harvest.harvest_date = harvest_date
    harvest.location = location
    harvest.crop_type = crop_type
    harvest.quantity_harvested = quantity_value
    harvest.unit = unit
    harvest.quality_grade = quality_grade
    harvest.workers_count = workers_count
    harvest.harvested_by = harvested_by
    harvest.supervised_by = supervised_by
    harvest.notes = notes

    try:
        with transaction.atomic():
            harvest.save()

            if schedule:
                schedule.status = HarvestSchedule.Status.COMPLETED
                schedule.save(update_fields=['status', 'updated_at'])

            if crop:
                crop.status = Crop.Status.HARVESTED
                crop.actual_harvest_date = harvest_date
                crop.save(update_fields=['status', 'actual_harvest_date', 'updated_at'])

            if previous_crop and previous_crop.pk != (crop.pk if crop else None):
                has_other_harvests = Harvest.objects.filter(crop=previous_crop).exclude(pk=harvest.pk).exists()
                if not has_other_harvests:
                    previous_crop.actual_harvest_date = None
                    if previous_crop.status == Crop.Status.HARVESTED:
                        previous_crop.status = Crop.Status.READY_FOR_HARVEST
                    previous_crop.save(update_fields=['status', 'actual_harvest_date', 'updated_at'])

            if previous_schedule and previous_schedule.pk != (schedule.pk if schedule else None):
                has_other_records = Harvest.objects.filter(
                    schedule=previous_schedule,
                ).exclude(pk=harvest.pk).exists()
                if not has_other_records and previous_schedule.status == HarvestSchedule.Status.COMPLETED:
                    previous_schedule.status = HarvestSchedule.Status.SCHEDULED
                    previous_schedule.save(update_fields=['status', 'updated_at'])
    except Exception:
        return JsonResponse(
            {'error': 'Could not save harvest record due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'Harvest record {harvest.harvest_code} for "{harvest.crop_type}" has been '
        f'{"updated" if is_update else "recorded"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_harvest_json(harvest),
    })


@login_required(login_url='login')
@require_POST
def harvest_delete_ajax(request, pk):
    """Delete a harvest record and release its linked schedule/crop."""
    harvest = get_object_or_404(
        Harvest.objects.select_related('schedule', 'crop'),
        pk=pk,
        user=request.user,
    )
    harvest_desc = harvest.harvest_code or str(harvest)
    schedule = harvest.schedule
    crop = harvest.crop
    harvest.delete()

    if schedule and schedule.status == HarvestSchedule.Status.COMPLETED:
        schedule.status = HarvestSchedule.Status.SCHEDULED
        schedule.save(update_fields=['status', 'updated_at'])

    if crop and not Harvest.objects.filter(crop=crop).exists():
        crop.actual_harvest_date = None
        if crop.status == Crop.Status.HARVESTED:
            crop.status = Crop.Status.READY_FOR_HARVEST
        crop.save(update_fields=['status', 'actual_harvest_date', 'updated_at'])

    messages.success(request, f'Harvest record "{harvest_desc}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Harvest record "{harvest_desc}" has been deleted successfully.',
    })


@login_required(login_url='login')
def harvest_schedule_list_ajax(request):
    """Return the signed-in user's harvest schedules as JSON."""
    status = request.GET.get('status', '').strip()
    schedules = get_harvest_schedules(request.user)

    valid_statuses = dict(HarvestSchedule.Status.choices)
    if status in valid_statuses:
        schedules = schedules.filter(status=status)

    schedules = list(schedules)
    return JsonResponse({
        'data': [_schedule_json(schedule) for schedule in schedules],
        'total': len(schedules),
    })


@login_required(login_url='login')
def harvest_schedule_get_ajax(request, pk):
    """Return one of the signed-in user's harvest schedules as JSON."""
    schedule = get_object_or_404(
        HarvestSchedule.objects.select_related('farm', 'crop', 'harvest_record'),
        pk=pk,
        user=request.user,
    )
    return JsonResponse(_schedule_json(schedule))


@login_required(login_url='login')
@require_POST
def harvest_schedule_save_ajax(request):
    """Validate and create or update a harvest schedule."""
    schedule_id = request.POST.get('id', '').strip()

    if schedule_id:
        schedule = get_object_or_404(HarvestSchedule, pk=schedule_id, user=request.user)
        is_update = True
    else:
        schedule = HarvestSchedule(user=request.user)
        is_update = False

    farm_id = request.POST.get('farm_id', '').strip()
    crop_id = request.POST.get('crop_id', '').strip()
    field_name = request.POST.get('field_name', '').strip()
    scheduled_date_raw = request.POST.get('scheduled_date', '').strip()
    expected_quantity_raw = request.POST.get('expected_quantity', '').strip()
    unit = request.POST.get('unit', '').strip()
    workers_raw = request.POST.get('workers_count', '').strip()
    assigned_to = request.POST.get('assigned_to', '').strip()
    supervisor = request.POST.get('supervisor', '').strip()
    status = request.POST.get('status', '').strip()
    notes = request.POST.get('notes', '').strip()

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

    if not field_name:
        return JsonResponse({'error': 'Field is required.'}, status=400)

    if not scheduled_date_raw:
        return JsonResponse({'error': 'Scheduled date is required.'}, status=400)
    scheduled_date = parse_date(scheduled_date_raw)
    if scheduled_date is None:
        return JsonResponse({'error': 'Enter a valid scheduled date.'}, status=400)

    expected_quantity = None
    if expected_quantity_raw:
        expected_quantity = _parse_decimal(expected_quantity_raw)
        if expected_quantity is None or expected_quantity < 0:
            return JsonResponse(
                {'error': 'Expected quantity must be a valid number (0 or greater).'},
                status=400,
            )

    workers_count = _parse_int(workers_raw)
    if workers_count is None or workers_count < 1:
        return JsonResponse(
            {'error': 'Please assign at least one worker to the harvest.'},
            status=400,
        )

    if not unit:
        unit = 'kg'

    valid_statuses = dict(HarvestSchedule.Status.choices)
    if status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid schedule status.'}, status=400)

    existing_record = _schedule_harvest_record(schedule) if schedule.pk else None
    if existing_record:
        if status != HarvestSchedule.Status.COMPLETED:
            return JsonResponse(
                {'error': f'This schedule is linked to harvest {existing_record.harvest_code}. '
                          'Delete that harvest record before reopening the schedule.'},
                status=400,
            )
        if schedule.farm_id != farm.id or schedule.crop_id != (crop.id if crop else None):
            return JsonResponse(
                {'error': 'This schedule already has a harvest record, so its farm and crop cannot be changed.'},
                status=400,
            )

    if crop and status in HarvestSchedule.STATUS_ACTIVE:
        duplicate = HarvestSchedule.objects.filter(
            user=request.user,
            crop=crop,
            status__in=HarvestSchedule.STATUS_ACTIVE,
        )
        if schedule.pk:
            duplicate = duplicate.exclude(pk=schedule.pk)
        if duplicate.exists():
            return JsonResponse(
                {'error': 'This crop already has an active harvest schedule. Edit that schedule instead.'},
                status=400,
            )

    schedule.farm = farm
    schedule.crop = crop
    schedule.field_name = field_name
    schedule.scheduled_date = scheduled_date
    schedule.expected_quantity = expected_quantity
    schedule.unit = unit
    schedule.workers_count = workers_count
    schedule.assigned_to = assigned_to
    schedule.supervisor = supervisor
    schedule.status = status
    schedule.notes = notes

    try:
        schedule.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save harvest schedule due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'Harvest schedule for "{field_name}" has been '
        f'{"updated" if is_update else "created"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_schedule_json(schedule),
    })


@login_required(login_url='login')
@require_POST
def harvest_schedule_delete_ajax(request, pk):
    """Delete a harvest schedule that has not yet produced a harvest record."""
    schedule = get_object_or_404(
        HarvestSchedule.objects.select_related('farm', 'crop', 'harvest_record'),
        pk=pk,
        user=request.user,
    )
    record = _schedule_harvest_record(schedule)
    if record:
        return JsonResponse(
            {'error': f'This schedule is linked to harvest {record.harvest_code}. Delete that harvest record first.'},
            status=400,
        )

    schedule_desc = str(schedule)
    schedule.delete()
    messages.success(request, f'Harvest schedule "{schedule_desc}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Harvest schedule "{schedule_desc}" has been deleted successfully.',
    })
