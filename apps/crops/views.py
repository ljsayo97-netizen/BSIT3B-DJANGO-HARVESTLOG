"""Crop management views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.harvests.services import evaluate_crop
from .categories import CATEGORY_RULES, infer_category
from .images import CROP_IMAGE_FALLBACK, CROP_IMAGE_RULES, crop_image_path
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


MAX_CROP_IMAGE_BYTES = 5 * 1024 * 1024


def _validate_crop_image(upload):
    """Return an error message when ``upload`` is not a usable image."""
    if upload.size > MAX_CROP_IMAGE_BYTES:
        return 'Crop photo must be 5 MB or smaller.'
    content_type = getattr(upload, 'content_type', '') or ''
    if content_type and not content_type.startswith('image/'):
        return 'Upload a valid image file (JPG, PNG, WebP, or GIF).'
    try:
        from PIL import Image

        with Image.open(upload) as image:
            image.verify()
    except Exception:
        return 'Upload a valid image file (JPG, PNG, WebP, or GIF).'
    upload.seek(0)
    return None


def _crop_json(crop):
    """Serialize a crop instance to a JSON-friendly dict."""
    return {
        'id': crop.id,
        'farm_id': crop.farm_id,
        'farm_name': crop.farm.name,
        'farm_location': crop.farm.location,
        'name': crop.name,
        'category': crop.category,
        'category_display': crop.get_category_display(),
        'variety': crop.variety,
        'image': crop.display_image_url,
        'image_is_upload': bool(crop.image),
        'estimated_yield': (
            float(crop.estimated_yield)
            if crop.estimated_yield is not None else None
        ),
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
        'harvest_progress': crop.harvest_progress,
        'created_at': crop.created_at.isoformat(),
    }


@login_required(login_url='login')
def crop_list_page(request):
    """Render the visual crop inventory for the signed-in user."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    farm_id = request.GET.get('farm', '').strip()
    category = request.GET.get('category', '').strip()

    farms = Farm.objects.filter(user=request.user).order_by('name')
    crops_list = (
        Crop.objects.filter(user=request.user)
        .select_related('farm')
        .order_by('-planting_date', '-created_at')
    )
    crops = list(crops_list)

    valid_statuses = dict(Crop.Status.choices)
    if status not in valid_statuses:
        status = ''
    valid_categories = dict(Crop.Category.choices)
    if category not in valid_categories:
        category = ''

    category_counts = {value: 0 for value in valid_categories}
    total_area = 0.0
    ready_count = 0
    for crop in crops:
        key = crop.category if crop.category in category_counts else Crop.Category.OTHER
        category_counts[key] += 1
        total_area += float(crop.area_hectares or 0)
        if crop.is_ready_for_harvest:
            ready_count += 1

    category_filters = [{
        'value': '',
        'label': 'All Crops',
        'count': len(crops),
    }]
    category_filters.extend({
        'value': value,
        'label': label,
        'count': category_counts.get(value, 0),
    } for value, label in Crop.Category.choices)

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

    crop_image_rules = [
        {
            'keywords': list(keywords),
            'url': static(image_path),
        }
        for keywords, image_path in CROP_IMAGE_RULES
    ]
    category_rules = [
        {
            'category': category_value,
            'keywords': list(keywords),
        }
        for category_value, keywords in CATEGORY_RULES
    ]

    return render(request, 'crops/list.html', {
        'crops': crops,
        'crop_count': len(crops),
        'total_area': round(total_area, 2),
        'ready_count': ready_count,
        'farms': farms,
        'query': query,
        'status': status,
        'farm_id': farm_id,
        'category': category,
        'status_choices': Crop.Status.choices,
        'category_choices': Crop.Category.choices,
        'category_filters': category_filters,
        'category_counts': category_counts,
        'quality_choices': Crop.Quality.choices,
        'farm_detail_id': farm_detail_id,
        'selected_farm': selected_farm,
        'farm_crops': farm_crops,
        'farm_history': farm_history,
        'default_maturity_days': DEFAULT_MATURITY_DAYS,
        'maturity_suggestions': CROP_MATURITY_DAYS,
        'crop_image_rules': crop_image_rules,
        'crop_image_fallback': static(CROP_IMAGE_FALLBACK),
        'category_rules': category_rules,
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


def _short_date(value):
    return value.strftime('%b %d, %Y') if value else ''


@login_required(login_url='login')
def crop_detail_ajax(request, pk):
    """Return the full inventory record for the crop details drawer."""
    crop = get_object_or_404(
        Crop.objects.select_related('farm'), pk=pk, user=request.user
    )
    area = float(crop.area_hectares or 0)

    harvest_records = []
    total_by_unit = {}
    harvest_qs = (
        crop.harvests.select_related('farm')
        .order_by('-harvest_date', '-created_at')
    )
    for harvest in harvest_qs:
        quantity = float(harvest.quantity_harvested or 0)
        unit = harvest.unit or 'kg'
        total_by_unit[unit] = total_by_unit.get(unit, 0) + quantity
        harvest_records.append({
            'id': harvest.id,
            'harvest_code': harvest.harvest_code or '',
            'harvest_date': _short_date(harvest.harvest_date),
            'quantity': round(quantity, 2),
            'unit': unit,
            'harvest_area': round(area, 2),
            'yield_per_hectare': round(quantity / area, 2) if area > 0 else None,
            'quality_grade': harvest.quality_grade,
            'quality_grade_display': harvest.get_quality_grade_display(),
            'quality_condition_display': (
                harvest.get_quality_condition_display()
                if harvest.quality_condition else ''
            ),
            'damaged_quantity': (
                float(harvest.damaged_quantity)
                if harvest.damaged_quantity is not None else None
            ),
            'location': harvest.location or '',
            'notes': harvest.notes or '',
        })

    activities = []
    for activity in crop.activities.select_related('farm').order_by('scheduled_date', 'id'):
        activities.append({
            'id': activity.id,
            'activity_type': activity.activity_type,
            'activity_type_display': activity.get_activity_type_display(),
            'scheduled_date': _short_date(activity.scheduled_date),
            'status': activity.status,
            'status_display': activity.get_status_display(),
            'priority_display': activity.get_priority_display(),
            'assigned_worker': activity.assigned_worker or '',
            'location': activity.location or '',
            'remarks': activity.remarks or '',
            'completed_at': (
                activity.completed_at.strftime('%b %d, %Y')
                if activity.completed_at else ''
            ),
        })

    milestones = [{
        'label': 'Planting',
        'date': _short_date(crop.planting_date),
        'tone': 'completed',
    }]
    if crop.expected_harvest_date:
        milestones.append({
            'label': 'Expected harvest',
            'date': _short_date(crop.expected_harvest_date),
            'tone': 'upcoming',
        })
    if crop.actual_harvest_date:
        milestones.append({
            'label': 'Harvested',
            'date': _short_date(crop.actual_harvest_date),
            'tone': 'completed',
        })

    return JsonResponse({
        'id': crop.id,
        'name': crop.name,
        'category': crop.category,
        'category_display': crop.get_category_display(),
        'variety': crop.variety or '',
        'image': crop.display_image_url,
        'image_is_upload': bool(crop.image),
        'farm_id': crop.farm_id,
        'farm_name': crop.farm.name if crop.farm else '',
        'farm_code': crop.farm.farm_code if crop.farm else '',
        'farm_location': crop.farm.location if crop.farm else '',
        'status': crop.status,
        'status_display': crop.get_status_display(),
        'quality_display': crop.get_quality_display() if crop.quality else '',
        'area_hectares': round(area, 2),
        'estimated_yield': (
            float(crop.estimated_yield)
            if crop.estimated_yield is not None else None
        ),
        'description': crop.notes or '',
        'planting_date': _short_date(crop.planting_date),
        'expected_harvest_date': _short_date(crop.expected_harvest_date),
        'actual_harvest_date': _short_date(crop.actual_harvest_date),
        'days_to_maturity': crop.days_to_maturity,
        'days_remaining': crop.days_to_harvest,
        'days_remaining_label': crop.days_to_harvest_label,
        'growth_stage': crop.maturity_label,
        'harvest_season': crop.harvest_season or '',
        'harvest_progress': crop.harvest_progress,
        'soil_type': None,
        'irrigation': None,
        'total_harvested': [
            {'quantity': round(quantity, 2), 'unit': unit}
            for unit, quantity in sorted(total_by_unit.items())
        ],
        'harvest_count': len(harvest_records),
        'harvest_records': harvest_records,
        'activity_count': len(activities),
        'activities': activities,
        'milestones': milestones,
    })


@login_required(login_url='login')
def crop_inventory_ajax(request):
    """Return all records of one crop (across farms) for the inventory modal."""
    name = request.GET.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Crop name is required.'}, status=400)

    crops = (
        Crop.objects.filter(user=request.user, name__iexact=name)
        .select_related('farm')
        .order_by('farm__name', 'expected_harvest_date', '-planting_date')
    )

    records = []
    farms = []
    seen_farms = set()
    total_area = 0.0
    for crop in crops:
        farm_name = crop.farm.name if crop.farm else 'Unknown farm'
        total_area += float(crop.area_hectares or 0)
        if crop.farm_id and crop.farm_id not in seen_farms:
            seen_farms.add(crop.farm_id)
            farms.append({
                'id': crop.farm_id,
                'name': farm_name,
                'location': crop.farm.location or '',
            })
        records.append({
            'id': crop.id,
            'name': crop.name,
            'farm_id': crop.farm_id,
            'farm_name': farm_name,
            'farm_location': crop.farm.location if crop.farm else '',
            'variety': crop.variety or '',
            'planting_date': _short_date(crop.planting_date),
            'harvest_date': _short_date(crop.expected_harvest_date),
            'actual_harvest_date': _short_date(crop.actual_harvest_date),
            'days_to_harvest_label': crop.days_to_harvest_label,
            'status': crop.status,
            'status_display': crop.get_status_display(),
            'area_hectares': float(crop.area_hectares or 0),
        })

    if not records:
        return JsonResponse(
            {'error': f'No crops found for "{name}".'}, status=404
        )

    return JsonResponse({
        'name': name,
        'image': static(crop_image_path(name)),
        'farm_count': len(farms),
        'farms': farms,
        'crop_count': len(records),
        'total_area': round(total_area, 2),
        'records': records,
    })


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
    category = request.POST.get('category', '').strip()
    variety = request.POST.get('variety', '').strip()
    planting_date_raw = request.POST.get('planting_date', '').strip()
    days_to_maturity_raw = request.POST.get('days_to_maturity', '').strip()
    status = request.POST.get('status', '').strip()
    quality = request.POST.get('quality', '').strip()
    area_raw = request.POST.get('area_hectares', '').strip()
    estimated_yield_raw = request.POST.get('estimated_yield', '').strip()
    description = request.POST.get('description', '').strip()
    crop_image = request.FILES.get('image')
    remove_image = request.POST.get('remove_image') == '1'
    old_image_name = crop.image.name if crop.image else None

    if not farm_id:
        return JsonResponse({'error': 'Please select a farm.'}, status=400)
    try:
        farm = Farm.objects.get(pk=farm_id, user=request.user)
    except Farm.DoesNotExist:
        return JsonResponse({'error': 'Selected farm does not exist.'}, status=400)

    if not name:
        return JsonResponse({'error': 'Crop name is required.'}, status=400)

    valid_categories = dict(Crop.Category.choices)
    if category:
        if category not in valid_categories:
            return JsonResponse({'error': 'Please select a valid crop category.'}, status=400)
    elif not is_update:
        category = infer_category(name)

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

    estimated_yield = None
    if 'estimated_yield' in request.POST:
        if estimated_yield_raw:
            estimated_yield = _parse_decimal(estimated_yield_raw)
            if estimated_yield is None or estimated_yield < 0:
                return JsonResponse(
                    {'error': 'Estimated yield must be a valid number (0 or greater).'},
                    status=400,
                )
    else:
        estimated_yield = crop.estimated_yield

    if crop_image:
        image_error = _validate_crop_image(crop_image)
        if image_error:
            return JsonResponse({'error': image_error}, status=400)

    crop.farm = farm
    crop.name = name
    crop.category = category or crop.category or Crop.Category.OTHER
    crop.variety = variety
    crop.planting_date = planting_date
    crop.days_to_maturity = days_to_maturity
    crop.area_hectares = area_value
    crop.estimated_yield = estimated_yield
    if 'description' in request.POST:
        crop.notes = description

    if crop_image:
        crop.image = crop_image
    elif remove_image:
        crop.image = None

    try:
        crop.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save crop due to a conflict.'},
            status=400,
        )

    new_image_name = crop.image.name if crop.image else None
    if old_image_name and old_image_name != new_image_name:
        default_storage.delete(old_image_name)

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
    image_name = crop.image.name if crop.image else None
    crop.delete()
    if image_name:
        default_storage.delete(image_name)
    messages.success(request, f'Crop "{crop_name}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Crop "{crop_name}" has been deleted successfully.',
    })
