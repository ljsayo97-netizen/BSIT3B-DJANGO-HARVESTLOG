"""Farm registration and management views."""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import Farm


def _parse_size(raw_size):
    """Convert a size value to a float, returning None when invalid."""
    try:
        value = float(raw_size)
    except (TypeError, ValueError):
        return None
    return value


def _farm_json(farm):
    """Serialize a farm instance to a JSON-friendly dict."""
    return {
        'id': farm.id,
        'name': farm.name,
        'owner': farm.owner,
        'location': farm.location,
        'size_hectares': float(farm.size_hectares),
        'description': farm.description,
        'date_registered': farm.date_registered.isoformat(),
        'status': farm.status,
        'status_display': farm.get_status_display(),
        'created_at': farm.created_at.isoformat(),
    }


@login_required(login_url='login')
def farm_list_page(request):
    """Render the searchable, filterable, paginated farm list for the signed-in user."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    farms_list = Farm.objects.filter(user=request.user).order_by('-date_registered')

    if query:
        farms_list = farms_list.filter(
            Q(name__icontains=query) |
            Q(owner__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )

    valid_statuses = dict(Farm.Status.choices)
    if status in valid_statuses:
        farms_list = farms_list.filter(status=status)

    paginator = Paginator(farms_list, 10)
    page_number = request.GET.get('page', 1)
    farms = paginator.get_page(page_number)

    return render(request, 'farms/list.html', {
        'farms': farms,
        'query': query,
        'status': status,
        'status_choices': Farm.Status.choices,
    })


@login_required(login_url='login')
def farm_list_ajax(request):
    """Return the signed-in user's filtered farms as paginated JSON."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    farms_list = Farm.objects.filter(user=request.user).order_by('-date_registered')

    if query:
        farms_list = farms_list.filter(
            Q(name__icontains=query) |
            Q(owner__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )

    valid_statuses = dict(Farm.Status.choices)
    if status in valid_statuses:
        farms_list = farms_list.filter(status=status)

    paginator = Paginator(farms_list, 10)
    page_number = request.GET.get('page', 1)
    farms = paginator.get_page(page_number)

    return JsonResponse({
        'data': [_farm_json(farm) for farm in farms.object_list],
        'has_next': farms.has_next(),
        'has_prev': farms.has_previous(),
        'page': farms.number,
        'pages': farms.paginator.num_pages,
        'total': farms.paginator.count,
    })


@login_required(login_url='login')
def farm_get_ajax(request, pk):
    """Return one of the signed-in user's farms as JSON (used for view/edit)."""
    farm = get_object_or_404(Farm, pk=pk, user=request.user)
    return JsonResponse(_farm_json(farm))


@login_required(login_url='login')
@require_POST
def farm_save_ajax(request):
    """Validate and create or update a farm, returning its data as JSON."""
    farm_id = request.POST.get('id', '').strip()

    if farm_id:
        farm = get_object_or_404(Farm, pk=farm_id, user=request.user)
        is_update = True
    else:
        farm = Farm(user=request.user)
        is_update = False

    name = request.POST.get('name', '').strip()
    owner = request.POST.get('owner', '').strip()
    location = request.POST.get('location', '').strip()
    size_raw = request.POST.get('size_hectares', '').strip()
    description = request.POST.get('description', '').strip()
    date_registered_raw = request.POST.get('date_registered', '').strip()
    status = request.POST.get('status', '').strip()

    if not name:
        return JsonResponse({'error': 'Farm name is required.'}, status=400)
    if not owner:
        return JsonResponse({'error': 'Owner / manager is required.'}, status=400)
    if not location:
        return JsonResponse({'error': 'Location is required.'}, status=400)

    size_value = _parse_size(size_raw)
    if size_value is None or size_value < 0:
        return JsonResponse(
            {'error': 'Farm size must be a valid number (0 or greater).'},
            status=400,
        )

    valid_statuses = dict(Farm.Status.choices)
    if status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid farm status.'}, status=400)

    if date_registered_raw:
        date_registered_value = parse_datetime(date_registered_raw)
        if date_registered_value is None:
            return JsonResponse(
                {'error': 'Enter a valid date registered.'},
                status=400,
            )
    else:
        date_registered_value = timezone.now()

    farm.name = name
    farm.owner = owner
    farm.location = location
    farm.size_hectares = size_value
    farm.description = description
    farm.date_registered = date_registered_value
    farm.status = status

    try:
        farm.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save farm due to a conflict.'},
            status=400,
        )

    messages.success(
        request,
        f'Farm "{farm.name}" has been {"updated" if is_update else "registered"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_farm_json(farm),
    })


@login_required(login_url='login')
@require_POST
def farm_delete_ajax(request, pk):
    """Delete the specified signed-in user's farm and confirm as JSON."""
    farm = get_object_or_404(Farm, pk=pk, user=request.user)
    farm_name = farm.name
    farm.delete()
    messages.success(request, f'Farm "{farm_name}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Farm "{farm_name}" has been deleted successfully.',
    })


@login_required(login_url='login')
@require_POST
def farm_archive_ajax(request, pk):
    """Archive the specified signed-in user's farm (sets status to Archived)."""
    farm = get_object_or_404(Farm, pk=pk, user=request.user)
    farm.status = Farm.Status.ARCHIVED
    farm.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Farm "{farm.name}" has been archived.')
    return JsonResponse({
        'status': 'archived',
        'message': f'Farm "{farm.name}" has been archived.',
    })
