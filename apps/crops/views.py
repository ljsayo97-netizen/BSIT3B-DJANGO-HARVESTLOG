"""Crop management views."""

from django.utils.dateparse import parse_date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.farms.models import Farm
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
        'expected_harvest_date': crop.expected_harvest_date.isoformat() if crop.expected_harvest_date else None,
        'actual_harvest_date': crop.actual_harvest_date.isoformat() if crop.actual_harvest_date else None,
        'status': crop.status,
        'status_display': crop.get_status_display(),
        'area_hectares': float(crop.area_hectares),
        'notes': crop.notes,
        'days_since_planting': crop.days_since_planting,
        'days_to_harvest': crop.days_to_harvest,
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

    return render(request, 'crops/list.html', {
        'crops': crops,
        'farms': farms,
        'query': query,
        'status': status,
        'farm_id': farm_id,
        'status_choices': Crop.Status.choices,
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
    expected_harvest_date_raw = request.POST.get('expected_harvest_date', '').strip()
    actual_harvest_date_raw = request.POST.get('actual_harvest_date', '').strip()
    status = request.POST.get('status', '').strip()
    area_raw = request.POST.get('area_hectares', '').strip()
    notes = request.POST.get('notes', '').strip()

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

    expected_harvest_date = None
    if expected_harvest_date_raw:
        expected_harvest_date = parse_date(expected_harvest_date_raw)
        if expected_harvest_date is None:
            return JsonResponse({'error': 'Enter a valid expected harvest date.'}, status=400)

    actual_harvest_date = None
    if actual_harvest_date_raw:
        actual_harvest_date = parse_date(actual_harvest_date_raw)
        if actual_harvest_date is None:
            return JsonResponse({'error': 'Enter a valid actual harvest date.'}, status=400)

    valid_statuses = dict(Crop.Status.choices)
    if status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid crop status.'}, status=400)

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
    crop.expected_harvest_date = expected_harvest_date
    crop.actual_harvest_date = actual_harvest_date
    crop.status = status
    crop.area_hectares = area_value
    crop.notes = notes

    try:
        crop.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save crop due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'Crop "{crop.name}" has been {"updated" if is_update else "added"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_crop_json(crop),
    })


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
