"""Crop-driven harvest recording, readiness, and history views."""

import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.crops.models import Crop
from apps.farms.models import Farm

from .models import Harvest, HarvestNotification
from .services import (
    evaluate_crop,
    get_harvest_board,
    get_topbar_notifications,
    get_unread_notification_count,
    mark_all_notifications_read,
    reopen_crop_notifications,
    resolve_crop_notifications,
)


def _parse_decimal(raw_value):
    """Convert a value to a decimal, returning None when invalid."""
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


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
            Q(quality_observations__icontains=query) |
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


def _harvest_json(harvest):
    """Serialize a harvest instance to a JSON-friendly dict."""
    return {
        'id': harvest.id,
        'harvest_code': harvest.harvest_code,
        'farm_id': harvest.farm_id,
        'farm_name': harvest.farm.name,
        'crop_id': harvest.crop_id,
        'crop_name': harvest.crop.name if harvest.crop else None,
        'harvest_season': harvest.harvest_season,
        'harvest_date': harvest.harvest_date.isoformat() if harvest.harvest_date else None,
        'location': harvest.location,
        'crop_type': harvest.crop_type,
        'quantity_harvested': float(harvest.quantity_harvested),
        'unit': harvest.unit,
        'quality_grade': harvest.quality_grade,
        'quality_grade_display': harvest.get_quality_grade_display(),
        'quality_condition': harvest.quality_condition,
        'quality_condition_display': harvest.get_quality_condition_display(),
        'moisture_level': (
            float(harvest.moisture_level) if harvest.moisture_level is not None else None
        ),
        'damaged_quantity': (
            float(harvest.damaged_quantity) if harvest.damaged_quantity is not None else None
        ),
        'quality_observations': harvest.quality_observations,
        'quality_recorded_at': (
            harvest.quality_recorded_at.isoformat() if harvest.quality_recorded_at else None
        ),
        'workers_count': harvest.workers_count,
        'harvested_by': harvest.harvested_by,
        'supervised_by': harvest.supervised_by,
        'notes': harvest.notes,
        'created_at': harvest.created_at.isoformat(),
    }


def _not_harvestable_message(crop):
    """Explain why a crop cannot be recorded as a harvest yet."""
    if crop.actual_harvest_date:
        return (
            f'This crop was already harvested on '
            f'{crop.actual_harvest_date:%b %d, %Y} and is not harvestable.'
        )
    if crop.expected_harvest_date:
        days = crop.days_to_harvest
        if days is not None and days > 0:
            return (
                'This crop is not ready for harvest yet. The system expects it to be '
                f'harvestable on {crop.expected_harvest_date:%b %d, %Y} '
                f'(in {days} day{"s" if days != 1 else ""}).'
            )
    return 'This crop is not ready for harvest yet.'


def _restore_crop_readiness(crop):
    """Return a crop to the harvest board after its harvest is removed."""
    if crop.status == Crop.Status.FAILED:
        return

    crop.actual_harvest_date = None
    days = crop.days_to_harvest
    if days is None or days <= 0:
        crop.status = Crop.Status.READY_FOR_HARVEST
    else:
        crop.status = Crop.Status.MATURING
    crop.save(update_fields=['status', 'actual_harvest_date', 'updated_at'])
    reopen_crop_notifications(crop)


@login_required(login_url='login')
def harvest_list_page(request):
    """Render crop readiness and harvest records."""
    harvests_list, filters = _filter_harvests(request)
    board = get_harvest_board(request.user)

    paginator = Paginator(harvests_list, 10)
    harvests = paginator.get_page(request.GET.get('page', 1))

    all_harvests = Harvest.objects.filter(user=request.user)
    total_harvests = all_harvests.count()
    unit_totals = list(
        all_harvests.values('unit')
        .annotate(total=Sum('quantity_harvested'))
        .order_by('-total', 'unit')
    )
    total_quantity = unit_totals[0]['total'] if unit_totals else 0
    total_unit = unit_totals[0]['unit'] if unit_totals else ''
    this_month_count = all_harvests.filter(
        harvest_date__gte=timezone.localdate().replace(day=1)
    ).count()

    return render(request, 'harvests/list.html', {
        'harvests': harvests,
        'farms': Farm.objects.filter(user=request.user).order_by('name'),
        'crops': board['crops'],
        'ready_crops': board['ready_crops'],
        'approaching_crops': board['approaching_crops'],
        'upcoming_crops': board['upcoming_crops'],
        'ready_count': board['ready_count'],
        'approaching_count': board['approaching_count'],
        'upcoming_count': board['upcoming_count'],
        'total_harvests': total_harvests,
        'total_quantity': total_quantity,
        'total_unit': total_unit,
        'this_month_harvest_count': this_month_count,
        'quality_choices': Harvest.QualityGrade.choices,
        'condition_choices': Harvest.Condition.choices,
        'today': timezone.localdate(),
        **filters,
    })


@login_required(login_url='login')
def harvest_list_ajax(request):
    """Return the signed-in user's filtered/sorted harvests as paginated JSON."""
    harvests_list, _ = _filter_harvests(request)

    paginator = Paginator(harvests_list, 10)
    harvests = paginator.get_page(request.GET.get('page', 1))

    return JsonResponse({
        'data': [_harvest_json(harvest) for harvest in harvests.object_list],
        'has_next': harvests.has_next(),
        'has_prev': harvests.has_previous(),
        'page': harvests.number,
        'pages': paginator.num_pages,
        'total': paginator.count,
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
        'condition_choices': Harvest.Condition.choices,
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
        'Harvest Season',
        'Quantity',
        'Unit',
        'Quality',
        'Condition',
        'Moisture (%)',
        'Damaged Quantity',
        'Quality Observations',
        'Workers',
        'Team Lead',
        'Supervisor',
        'Remarks',
    ])

    records = harvests_list.select_related('farm', 'crop')
    for harvest in records.iterator():
        writer.writerow([
            _csv_value(harvest.harvest_code),
            harvest.harvest_date.isoformat() if harvest.harvest_date else '',
            _csv_value(harvest.farm.name),
            _csv_value(harvest.location),
            _csv_value(harvest.crop.name if harvest.crop else ''),
            _csv_value(harvest.crop_type),
            _csv_value(harvest.harvest_season),
            harvest.quantity_harvested,
            _csv_value(harvest.unit),
            _csv_value(harvest.get_quality_grade_display()),
            _csv_value(harvest.get_quality_condition_display() if harvest.quality_condition else ''),
            '' if harvest.moisture_level is None else harvest.moisture_level,
            '' if harvest.damaged_quantity is None else harvest.damaged_quantity,
            _csv_value(harvest.quality_observations),
            harvest.workers_count,
            _csv_value(harvest.harvested_by),
            _csv_value(harvest.supervised_by),
            _csv_value(harvest.notes),
        ])

    return response


@login_required(login_url='login')
@require_POST
def harvest_quality_save_ajax(request):
    """Document the quality of one of the user's harvests after the fact."""
    harvest_id = request.POST.get('id', '').strip()
    if not harvest_id:
        return JsonResponse({'error': 'Harvest record is required.'}, status=400)

    harvest = get_object_or_404(Harvest, pk=harvest_id, user=request.user)

    quality_grade = request.POST.get('quality_grade', '').strip()
    quality_condition = request.POST.get('quality_condition', '').strip()
    moisture_raw = request.POST.get('moisture_level', '').strip()
    damaged_raw = request.POST.get('damaged_quantity', '').strip()
    observations = request.POST.get('quality_observations', '').strip()

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality_grade not in valid_grades:
        return JsonResponse({'error': 'Please select a valid quality grade.'}, status=400)

    valid_conditions = dict(Harvest.Condition.choices)
    if quality_condition and quality_condition not in valid_conditions:
        return JsonResponse({'error': 'Please select a valid condition.'}, status=400)

    moisture_level = None
    if moisture_raw:
        moisture_level = _parse_decimal(moisture_raw)
        if moisture_level is None or moisture_level < 0 or moisture_level > 100:
            return JsonResponse(
                {'error': 'Moisture level must be a number between 0 and 100.'},
                status=400,
            )

    damaged_quantity = None
    if damaged_raw:
        damaged_quantity = _parse_decimal(damaged_raw)
        if damaged_quantity is None or damaged_quantity < 0:
            return JsonResponse(
                {'error': 'Damaged quantity must be a valid number (0 or greater).'},
                status=400,
            )

    harvest.quality_grade = quality_grade
    harvest.quality_condition = quality_condition
    harvest.moisture_level = moisture_level
    harvest.damaged_quantity = damaged_quantity
    harvest.quality_observations = observations
    harvest.quality_recorded_at = timezone.now()
    harvest.save(update_fields=[
        'quality_grade',
        'quality_condition',
        'moisture_level',
        'damaged_quantity',
        'quality_observations',
        'quality_recorded_at',
        'updated_at',
    ])

    messages.success(
        request,
        f'Quality & observations recorded for harvest {harvest.harvest_code}.',
    )

    return JsonResponse({
        'status': 'success',
        'harvest_code': harvest.harvest_code,
        'quality_grade': harvest.quality_grade,
        'quality_grade_display': harvest.get_quality_grade_display(),
        'quality_condition': harvest.quality_condition,
        'quality_condition_display': harvest.get_quality_condition_display(),
        'moisture_level': (
            float(harvest.moisture_level) if harvest.moisture_level is not None else None
        ),
        'damaged_quantity': (
            float(harvest.damaged_quantity) if harvest.damaged_quantity is not None else None
        ),
        'quality_observations': harvest.quality_observations,
        'quality_recorded_at': harvest.quality_recorded_at.isoformat(),
        'quality_details': harvest.quality_details,
    })


@login_required(login_url='login')
def harvest_get_ajax(request, pk):
    """Return one of the signed-in user's harvest records as JSON."""
    harvest = get_object_or_404(
        Harvest.objects.select_related('farm', 'crop'),
        pk=pk,
        user=request.user,
    )
    return JsonResponse(_harvest_json(harvest))


@login_required(login_url='login')
@require_POST
def harvest_save_ajax(request):
    """Record or update a harvest; the system supplies the harvest date."""
    harvest_id = request.POST.get('id', '').strip()

    if harvest_id:
        harvest = get_object_or_404(Harvest, pk=harvest_id, user=request.user)
        is_update = True
        previous_crop = harvest.crop
    else:
        harvest = Harvest(user=request.user)
        is_update = False
        previous_crop = None

    crop_id = request.POST.get('crop_id', '').strip()
    crop = None
    if crop_id:
        try:
            crop = Crop.objects.select_related('farm').get(pk=crop_id, user=request.user)
        except Crop.DoesNotExist:
            return JsonResponse({'error': 'Selected crop does not exist.'}, status=400)
    elif is_update:
        # Legacy records may not have a crop; keep their original link.
        crop = harvest.crop
    else:
        return JsonResponse({'error': 'Please select the crop being harvested.'}, status=400)

    if crop and crop.status == Crop.Status.FAILED:
        return JsonResponse(
            {'error': 'This crop was marked as damaged/failed and cannot be harvested.'},
            status=400,
        )

    if crop:
        other_harvests = Harvest.objects.filter(crop=crop)
        if is_update:
            other_harvests = other_harvests.exclude(pk=harvest.pk)
        if other_harvests.exists():
            return JsonResponse(
                {'error': 'This crop already has a harvest record.'},
                status=400,
            )

    # Only harvestable crops are inserted into the harvest records. An
    # existing harvest keeps its original crop even after it has been marked
    # harvested, so editing a record does not require it to be ready again.
    keep_existing_crop = (
        is_update
        and crop is not None
        and previous_crop is not None
        and crop.pk == previous_crop.pk
    )
    if crop and not keep_existing_crop:
        evaluate_crop(crop)
        if not crop.is_ready_for_harvest:
            return JsonResponse(
                {'error': _not_harvestable_message(crop)},
                status=400,
            )

    if crop:
        farm = crop.farm
    elif is_update:
        farm = harvest.farm
    else:
        return JsonResponse({'error': 'Please select the crop being harvested.'}, status=400)

    quantity_raw = request.POST.get('quantity_harvested', '').strip()
    unit = request.POST.get('unit', '').strip()
    quality_grade = request.POST.get('quality_grade', '').strip()
    quality_condition = request.POST.get('quality_condition', '').strip()
    moisture_raw = request.POST.get('moisture_level', '').strip()
    damaged_raw = request.POST.get('damaged_quantity', '').strip()
    quality_observations = request.POST.get('quality_observations', '').strip()
    workers_raw = request.POST.get('workers_count', '').strip()
    harvested_by = request.POST.get('harvested_by', '').strip()
    supervised_by = request.POST.get('supervised_by', '').strip()
    notes = request.POST.get('notes', '').strip()

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

    valid_conditions = dict(Harvest.Condition.choices)
    if quality_condition and quality_condition not in valid_conditions:
        return JsonResponse({'error': 'Please select a valid condition.'}, status=400)

    moisture_level = None
    if moisture_raw:
        moisture_level = _parse_decimal(moisture_raw)
        if moisture_level is None or moisture_level < 0 or moisture_level > 100:
            return JsonResponse(
                {'error': 'Moisture level must be a number between 0 and 100.'},
                status=400,
            )

    damaged_quantity = None
    if damaged_raw:
        damaged_quantity = _parse_decimal(damaged_raw)
        if damaged_quantity is None or damaged_quantity < 0:
            return JsonResponse(
                {'error': 'Damaged quantity must be a valid number (0 or greater).'},
                status=400,
            )

    if not harvested_by:
        return JsonResponse({'error': 'Harvest team lead is required.'}, status=400)

    harvest.farm = farm
    harvest.crop = crop
    harvest.location = (farm.location or farm.name)
    harvest.crop_type = crop.name if crop else harvest.crop_type
    harvest.quantity_harvested = quantity_value
    harvest.unit = unit
    harvest.quality_grade = quality_grade
    harvest.quality_condition = quality_condition
    harvest.moisture_level = moisture_level
    harvest.damaged_quantity = damaged_quantity
    harvest.quality_observations = quality_observations
    harvest.workers_count = workers_count
    harvest.harvested_by = harvested_by
    harvest.supervised_by = supervised_by
    harvest.notes = notes

    if crop and crop.harvest_season:
        harvest.harvest_season = crop.harvest_season

    # The user never enters a harvest date. New records always receive the
    # current date, while edits keep the date originally assigned.
    if not is_update:
        harvest.harvest_date = timezone.localdate()

    try:
        with transaction.atomic():
            harvest.save()

            if crop:
                crop.status = Crop.Status.HARVESTED
                crop.actual_harvest_date = harvest.harvest_date
                crop.save(update_fields=['status', 'actual_harvest_date', 'updated_at'])
                resolve_crop_notifications(crop)

            if previous_crop and previous_crop.pk != (crop.pk if crop else None):
                has_other_harvests = Harvest.objects.filter(
                    crop=previous_crop
                ).exclude(pk=harvest.pk).exists()
                if not has_other_harvests:
                    _restore_crop_readiness(previous_crop)
    except Exception:
        return JsonResponse(
            {'error': 'Could not save the harvest record due to a conflict.'},
            status=400,
        )

    action = 'updated' if is_update else 'recorded'
    messages.success(
        request,
        f'Harvest {harvest.harvest_code} for "{harvest.crop_type}" has been '
        f'{action} successfully. The system assigned {harvest.harvest_date:%b %d, %Y} '
        f'as the harvest date.',
    )

    return JsonResponse({
        'status': 'success',
        **_harvest_json(harvest),
    })


@login_required(login_url='login')
@require_POST
def harvest_delete_ajax(request, pk):
    """Delete a harvest record and return its crop to harvest readiness."""
    harvest = get_object_or_404(
        Harvest.objects.select_related('crop'),
        pk=pk,
        user=request.user,
    )
    harvest_desc = harvest.harvest_code or str(harvest)
    crop = harvest.crop
    harvest.delete()

    if crop and not Harvest.objects.filter(crop=crop).exists():
        _restore_crop_readiness(crop)

    messages.success(request, f'Harvest record "{harvest_desc}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Harvest record "{harvest_desc}" has been deleted successfully.',
    })


@login_required(login_url='login')
@require_POST
def harvest_notification_read_ajax(request):
    """Mark one notification, or every notification, as read."""
    notification_id = request.POST.get('id', '').strip()

    if notification_id:
        notification = get_object_or_404(
            HarvestNotification,
            pk=notification_id,
            user=request.user,
        )
        notification.mark_read()
        messages.success(request, 'Harvest notification marked as read.')
    else:
        mark_all_notifications_read(request.user)
        messages.success(request, 'All harvest notifications marked as read.')

    unread_count = get_unread_notification_count(request.user)

    # The dashboard notification center uses a plain HTML form and expects a
    # redirect back, while fetch() callers expect JSON.
    if 'text/html' in request.headers.get('Accept', ''):
        next_url = (
            request.POST.get('next')
            or request.META.get('HTTP_REFERER')
            or reverse('dashboard')
        )
        return redirect(next_url)

    return JsonResponse({
        'status': 'success',
        'unread_count': unread_count,
    })


@login_required(login_url='login')
@require_POST
def harvest_refresh_readiness_ajax(request):
    """Run a manual readiness check and return the resulting counts."""
    board = get_harvest_board(request.user)
    messages.success(
        request,
        f'Readiness check completed. {board["ready_count"]} crop(s) ready for harvest.',
    )
    return JsonResponse({
        'status': 'success',
        'ready_count': board['ready_count'],
        'approaching_count': board['approaching_count'],
        'upcoming_count': board['upcoming_count'],
        'unread_count': get_unread_notification_count(request.user),
    })


@login_required(login_url='login')
def topbar_notifications_ajax(request):
    """Return JSON feed for the topbar notifications dropdown."""
    from django.utils.timesince import timesince

    items = get_topbar_notifications(request.user, limit=8)
    unread_count = get_unread_notification_count(request.user)

    data = []
    for item in items:
        ts = item.get('timestamp')
        data.append({
            'id': item.get('id'),
            'title': item.get('title'),
            'badge': item.get('badge', ''),
            'description': item.get('description', ''),
            'meta': item.get('meta', ''),
            'time_ago': f'{timesince(ts)} ago' if ts else '',
            'icon': item.get('icon', 'fas fa-bell'),
            'tone': item.get('tone', 'info'),
            'url': item.get('url', '#'),
            'is_unread': bool(item.get('is_unread')),
            'can_mark_read': bool(item.get('can_mark_read')),
        })

    return JsonResponse({
        'status': 'success',
        'unread_count': unread_count,
        'notifications': data,
    })
