"""Harvest recording and history views."""

from django.utils.dateparse import parse_date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.farms.models import Farm
from apps.crops.models import Crop
from .models import Harvest


def _parse_decimal(raw_value):
    """Convert a value to a decimal, returning None when invalid."""
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def _harvest_json(harvest):
    """Serialize a harvest instance to a JSON-friendly dict."""
    return {
        'id': harvest.id,
        'farm_id': harvest.farm_id,
        'farm_name': harvest.farm.name,
        'crop_id': harvest.crop_id,
        'crop_name': harvest.crop.name if harvest.crop else None,
        'harvest_date': harvest.harvest_date.isoformat() if harvest.harvest_date else None,
        'location': harvest.location,
        'crop_type': harvest.crop_type,
        'quantity_harvested': float(harvest.quantity_harvested),
        'unit': harvest.unit,
        'quality_grade': harvest.quality_grade,
        'quality_grade_display': harvest.get_quality_grade_display(),
        'harvested_by': harvest.harvested_by,
        'supervised_by': harvest.supervised_by,
        'notes': harvest.notes,
        'created_at': harvest.created_at.isoformat(),
    }


@login_required(login_url='login')
def harvest_list_page(request):
    """Render the searchable, filterable, sortable harvest history list."""
    query = request.GET.get('q', '').strip()
    quality = request.GET.get('quality', '').strip()
    farm_id = request.GET.get('farm', '').strip()
    sort = request.GET.get('sort', '-harvest_date').strip()

    farms = Farm.objects.filter(user=request.user).order_by('name')
    crops = Crop.objects.filter(user=request.user).order_by('name')
    harvests_list = Harvest.objects.filter(user=request.user).select_related('farm', 'crop').order_by('-harvest_date')

    if query:
        harvests_list = harvests_list.filter(
            Q(crop_type__icontains=query) |
            Q(location__icontains=query) |
            Q(harvested_by__icontains=query) |
            Q(supervised_by__icontains=query) |
            Q(notes__icontains=query) |
            Q(farm__name__icontains=query)
        )

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality in valid_grades:
        harvests_list = harvests_list.filter(quality_grade=quality)

    if farm_id:
        try:
            harvests_list = harvests_list.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    # Sorting
    allowed_sorts = {
        'harvest_date': 'harvest_date',
        '-harvest_date': '-harvest_date',
        'crop_type': 'crop_type',
        '-crop_type': '-crop_type',
        'farm': 'farm__name',
        '-farm': '-farm__name',
        'quantity': 'quantity_harvested',
        '-quantity': '-quantity_harvested',
    }
    order_by = allowed_sorts.get(sort, '-harvest_date')
    harvests_list = harvests_list.order_by(order_by)

    paginator = Paginator(harvests_list, 10)
    page_number = request.GET.get('page', 1)
    harvests = paginator.get_page(page_number)

    return render(request, 'harvests/list.html', {
        'harvests': harvests,
        'farms': farms,
        'crops': crops,
        'query': query,
        'quality': quality,
        'farm_id': farm_id,
        'sort': sort,
        'quality_choices': Harvest.QualityGrade.choices,
        'current_sort': sort,
    })


@login_required(login_url='login')
def harvest_list_ajax(request):
    """Return the signed-in user's filtered/sorted harvests as paginated JSON."""
    query = request.GET.get('q', '').strip()
    quality = request.GET.get('quality', '').strip()
    farm_id = request.GET.get('farm', '').strip()
    sort = request.GET.get('sort', '-harvest_date').strip()

    harvests_list = Harvest.objects.filter(user=request.user).select_related('farm', 'crop').order_by('-harvest_date')

    if query:
        harvests_list = harvests_list.filter(
            Q(crop_type__icontains=query) |
            Q(location__icontains=query) |
            Q(harvested_by__icontains=query) |
            Q(supervised_by__icontains=query) |
            Q(notes__icontains=query) |
            Q(farm__name__icontains=query)
        )

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality in valid_grades:
        harvests_list = harvests_list.filter(quality_grade=quality)

    if farm_id:
        try:
            harvests_list = harvests_list.filter(farm_id=int(farm_id))
        except ValueError:
            pass

    allowed_sorts = {
        'harvest_date': 'harvest_date',
        '-harvest_date': '-harvest_date',
        'crop_type': 'crop_type',
        '-crop_type': '-crop_type',
        'farm': 'farm__name',
        '-farm': '-farm__name',
        'quantity': 'quantity_harvested',
        '-quantity': '-quantity_harvested',
    }
    order_by = allowed_sorts.get(sort, '-harvest_date')
    harvests_list = harvests_list.order_by(order_by)

    paginator = Paginator(harvests_list, 10)
    page_number = request.GET.get('page', 1)
    harvests = paginator.get_page(page_number)

    return JsonResponse({
        'data': [_harvest_json(h) for h in harvests.object_list],
        'has_next': harvests.has_next(),
        'has_prev': harvests.has_previous(),
        'page': harvests.number,
        'pages': harvests.paginator.num_pages,
        'total': harvests.paginator.count,
    })


@login_required(login_url='login')
def harvest_get_ajax(request, pk):
    """Return one of the signed-in user's harvest records as JSON."""
    harvest = get_object_or_404(Harvest, pk=pk, user=request.user)
    return JsonResponse(_harvest_json(harvest))


@login_required(login_url='login')
@require_POST
def harvest_save_ajax(request):
    """Validate and create or update a harvest record, returning its data as JSON."""
    harvest_id = request.POST.get('id', '').strip()

    if harvest_id:
        harvest = get_object_or_404(Harvest, pk=harvest_id, user=request.user)
        is_update = True
    else:
        harvest = Harvest(user=request.user)
        is_update = False

    farm_id = request.POST.get('farm_id', '').strip()
    crop_id = request.POST.get('crop_id', '').strip()
    harvest_date_raw = request.POST.get('harvest_date', '').strip()
    location = request.POST.get('location', '').strip()
    crop_type = request.POST.get('crop_type', '').strip()
    quantity_raw = request.POST.get('quantity_harvested', '').strip()
    unit = request.POST.get('unit', '').strip()
    quality_grade = request.POST.get('quality_grade', '').strip()
    harvested_by = request.POST.get('harvested_by', '').strip()
    supervised_by = request.POST.get('supervised_by', '').strip()
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

    if not harvest_date_raw:
        return JsonResponse({'error': 'Harvest date is required.'}, status=400)
    harvest_date = parse_date(harvest_date_raw)
    if harvest_date is None:
        return JsonResponse({'error': 'Enter a valid harvest date.'}, status=400)

    if not location:
        return JsonResponse({'error': 'Harvest location is required.'}, status=400)
    if not crop_type:
        return JsonResponse({'error': 'Crop type is required.'}, status=400)

    quantity_value = _parse_decimal(quantity_raw)
    if quantity_value is None or quantity_value < 0:
        return JsonResponse(
            {'error': 'Quantity must be a valid number (0 or greater).'},
            status=400,
        )

    if not unit:
        unit = 'kg'

    valid_grades = dict(Harvest.QualityGrade.choices)
    if quality_grade not in valid_grades:
        return JsonResponse({'error': 'Please select a valid quality grade.'}, status=400)

    if not harvested_by:
        return JsonResponse({'error': 'Harvested by (person) is required.'}, status=400)

    harvest.farm = farm
    harvest.crop = crop
    harvest.harvest_date = harvest_date
    harvest.location = location
    harvest.crop_type = crop_type
    harvest.quantity_harvested = quantity_value
    harvest.unit = unit
    harvest.quality_grade = quality_grade
    harvest.harvested_by = harvested_by
    harvest.supervised_by = supervised_by
    harvest.notes = notes

    try:
        harvest.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save harvest record due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'Harvest record for "{harvest.crop_type}" has been {"updated" if is_update else "recorded"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_harvest_json(harvest),
    })


@login_required(login_url='login')
@require_POST
def harvest_delete_ajax(request, pk):
    """Delete the specified signed-in user's harvest record and confirm as JSON."""
    harvest = get_object_or_404(Harvest, pk=pk, user=request.user)
    harvest_desc = str(harvest)
    harvest.delete()
    messages.success(request, f'Harvest record "{harvest_desc}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Harvest record "{harvest_desc}" has been deleted successfully.',
    })
