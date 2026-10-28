"""Crop management views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.harvests.services import evaluate_crop
from .maturity import (
    CROP_MATURITY_DAYS,
    DEFAULT_MATURITY_DAYS,
    suggest_maturity_days,
)
from .models import Crop


def _parse_decimal(raw_value):
    """Convert a value to a decimal, returning None when invalid."""
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def _crop_json(crop):
    """Serialize a crop instance to a JSON-friendly dict."""
    return {
        'id': crop.id,
        'farm_id': crop.farm_id,
        'farm_name': crop.farm.name,
        'name': crop.name,
        'variety': crop.variety,
        'planting_date': crop.planting_date.isoformat() if crop.planting_date else None,
        'days_to_maturity': crop.days_to_maturity,
        'expected_harvest_date': crop.expected_harvest_date.isoformat() if crop.expected_harvest_date else None,
        'actual_harvest_date': crop.actual_harvest_date.isoformat() if crop.actual_harvest_date else None,
        'harvest_season': getattr(crop, 'harvest_season', ''),
        'status': crop.status,
        'status_display': crop.get_status_display(),
        'quality': crop.quality,
        'quality_display': crop.get_quality_display(),
        'area_hectares': float(crop.area_hectares),
        'notes': crop.notes,
        'days_since_planting': crop.days_since_planting,
        'days_to_harvest': crop.days_to_harvest,
        'days_to_harvest_label': crop.days_to_harvest_label,
        'maturity_status': crop.maturity_status,
        'maturity_label': crop.maturity_label,
        'created_at': crop.created_at.isoformat(),
    }


@login_required(login_url='login')
def crop_list_page(request):
    """Render the searchable, filterable, paginated crop list for the signed-in user."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    farm_id = request.GET.get('farm', '').strip()

    farms = Farm.objects.filter(user=request.user).order_by('name')
    crops_list = Crop.objects.filter(user=request.user).select_related('farm').order_by('-planting_date')

    if query:
        crops_list = crops_list.filter(
            Q(name__icontains=query) |
            Q(variety__icontains=query) |
            Q(farm__name__icontains=query) |
            Q(notes__icontains=query)
        )

    valid_statuses = dict(Crop.Status.choices)
    if status in valid_statuses:
        crops_list = crops_list.filter(status=status)

    if farm_id:
        try:
            crops_list = crops_list.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    paginator = Paginator(crops_list, 10)
    page_number = request.GET.get('page', 1)
    crops = paginator.get_page(page_number)

    # Farm detail panel: show the selected farm's details, active crops, and
    # crop history (harvested / damaged-failed crops).
    farm_detail_id = request.GET.get('farm_detail', '').strip()
    selected_farm = None
    farm_crops = []
    farm_history = []
    if farm_detail_id.isdigit():
        selected_farm = Farm.objects.filter(pk=int(farm_detail_id), user=request.user).first()
        if selected_farm:
            farm_qs = Crop.objects.filter(farm=selected_farm, user=request.user)
            history_statuses = (Crop.Status.HARVESTED, Crop.Status.FAILED)
            farm_crops = farm_qs.exclude(status__in=history_statuses)
            farm_history = list(farm_qs.filter(status__in=history_statuses))

            # Attach each history crop's most recent harvest quality record.
            if farm_history:
                latest_quality = {}
                harvest_qs = Harvest.objects.filter(
                    user=request.user,
                    crop_id__in=[crop.pk for crop in farm_history],
                ).order_by('-harvest_date', '-created_at')
                for harvest in harvest_qs:
                    latest_quality.setdefault(harvest.crop_id, harvest)
                for crop in farm_history:
                    crop.latest_quality = latest_quality.get(crop.pk)

    return render(request, 'crops/list.html', {
        'crops': crops,
        'farms': farms,
        'query': query,
        'status': status,
        'farm_id': farm_id,
        'status_choices': Crop.Status.choices,
        'quality_choices': Crop.Quality.choices,
        'farm_detail_id': farm_detail_id,
        'selected_farm': selected_farm,
        'farm_crops': farm_crops,
        'farm_history': farm_history,
        'default_maturity_days': DEFAULT_MATURITY_DAYS,
        'maturity_suggestions': CROP_MATURITY_DAYS,
    })


@login_required(login_url='login')
def crop_list_ajax(request):
    """Return the signed-in user's filtered crops as paginated JSON."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    farm_id = request.GET.get('farm', '').strip()

    crops_list = Crop.objects.filter(user=request.user).select_related('farm').order_by('-planting_date')

    if query:
        crops_list = crops_list.filter(
            Q(name__icontains=query) |
            Q(variety__icontains=query) |
            Q(farm__name__icontains=query) |
            Q(notes__icontains=query)
        )

    valid_statuses = dict(Crop.Status.choices)
    if status in valid_statuses:
        crops_list = crops_list.filter(status=status)

    if farm_id:
        try:
            crops_list = crops_list.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    paginator = Paginator(crops_list, 10)
    page_number = request.GET.get('page', 1)
    crops = paginator.get_page(page_number)

    return JsonResponse({
        'data': [_crop_json(crop) for crop in crops.object_list],
        'has_next': crops.has_next(),
        'has_prev': crops.has_previous(),
        'page': crops.number,
        'pages': crops.paginator.num_pages,
        'total': crops.paginator.count,
    })


@login_required(login_url='login')
def crop_get_ajax(request, pk):
    """Return one of the signed-in user's crops as JSON."""
    crop = get_object_or_404(Crop, pk=pk, user=request.user)
    return JsonResponse(_crop_json(crop))


@login_required(login_url='login')
@require_POST
def crop_save_ajax(request):
    """Validate and create or update a crop, returning its data as JSON."""
    crop_id = request.POST.get('id', '').strip()

    if crop_id:
        crop = get_object_or_404(Crop, pk=crop_id, user=request.user)
        is_update = True
    else:
        crop = Crop(user=request.user)
        is_update = False

    farm_id = request.POST.get('farm_id', '').strip()
    name = request.POST.get('name', '').strip()
    variety = request.POST.get('variety', '').strip()
    planting_date_raw = request.POST.get('planting_date', '').strip()
    days_to_maturity_raw = request.POST.get('days_to_maturity', '').strip()
    status = request.POST.get('status', '').strip()
    quality = request.POST.get('quality', '').strip()
    area_raw = request.POST.get('area_hectares', '').strip()

    if not farm_id:
        return JsonResponse({'error': 'Please select a farm.'}, status=400)
    try:
        farm = Farm.objects.get(pk=farm_id, user=request.user)
    except Farm.DoesNotExist:
        return JsonResponse({'error': 'Selected farm does not exist.'}, status=400)

    if not name:
        return JsonResponse({'error': 'Crop name is required.'}, status=400)

    planting_date = None
    if planting_date_raw:
        planting_date = parse_date(planting_date_raw)
        if planting_date is None:
            return JsonResponse({'error': 'Enter a valid planting date.'}, status=400)
    else:
        return JsonResponse({'error': 'Planting date is required.'}, status=400)

    days_to_maturity = None
    if days_to_maturity_raw:
        try:
            days_to_maturity = int(days_to_maturity_raw)
        except (TypeError, ValueError):
            days_to_maturity = None
        if days_to_maturity is None or days_to_maturity < 1:
            return JsonResponse(
                {'error': 'Days to maturity must be a whole number of at least 1.'},
                status=400,
            )

    # The crop form no longer collects a harvest date. The system derives it
    # from the planting date and days to maturity (or the crop's estimate when
    # the grower leaves the field blank).
    if days_to_maturity is None:
        days_to_maturity = suggest_maturity_days(name)

    # Notes and the actual harvest date are no longer part of the crop form:
    # existing values are kept as-is (the actual harvest date is set
    # automatically when a harvest is recorded).
    if status:
        valid_statuses = dict(Crop.Status.choices)
        if status not in valid_statuses:
            return JsonResponse({'error': 'Please select a valid crop status.'}, status=400)
        crop.status = status
    elif not is_update:
        crop.status = Crop.Status.PLANTING

    if quality:
        valid_qualities = dict(Crop.Quality.choices)
        if quality not in valid_qualities:
            return JsonResponse({'error': 'Please select a valid quality grade.'}, status=400)
        crop.quality = quality
    else:
        crop.quality = ''

    area_value = _parse_decimal(area_raw)
    if area_value is None or area_value < 0:
        return JsonResponse(
            {'error': 'Area must be a valid number (0 or greater).'},
            status=400,
        )

    crop.farm = farm
    crop.name = name
    crop.variety = variety
    crop.planting_date = planting_date
    crop.days_to_maturity = days_to_maturity
    crop.area_hectares = area_value

    try:
        crop.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save crop due to a conflict.'},
            status=400,
        )

    # Evaluate readiness immediately so a crop that is already mature gets a
    # notification the moment it is added or edited.
    readiness = evaluate_crop(crop)

    expected_label = (
        crop.expected_harvest_date.strftime('%b %d, %Y')
        if crop.expected_harvest_date else 'not set'
    )
    detail = ''
    if readiness['status'] == 'ready':
        detail = (
            f' It is ready for harvest now; the system assigned '
            f'{expected_label} as its harvest date.'
        )
    elif readiness['status'] == 'approaching':
        detail = (
            f' It will be ready for harvest {crop.days_to_harvest_label.lower()} '
            f'({expected_label}).'
        )
    elif readiness['status'] == 'upcoming':
        detail = (
            f' The system assigned {expected_label} as its harvest date '
            f'({crop.days_to_harvest_label.lower()}).'
        )

    messages.success(
        request,
        f'Crop "{crop.name}" has been {"updated" if is_update else "added"} '
        f'successfully.{detail}',
    )

    payload = _crop_json(crop)
    payload.update({
        'status': 'success',
        'crop_status': crop.status,
        'readiness': readiness['status'],
        'notification_created': readiness['notification_created'],
    })
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def crop_delete_ajax(request, pk):
    """Delete the specified signed-in user's crop and confirm as JSON."""
    crop = get_object_or_404(Crop, pk=pk, user=request.user)
    crop_name = str(crop)
    crop.delete()
    messages.success(request, f'Crop "{crop_name}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Crop "{crop_name}" has been deleted successfully.',
    })
