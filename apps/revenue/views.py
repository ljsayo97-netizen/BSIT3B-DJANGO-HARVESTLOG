"""Revenue tracking views for crops and their planted hectares."""

import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.crops.models import Crop
from apps.farms.models import Farm

from .analytics import build_revenue_analytics_context
from .models import Revenue
from .services import (
    DEFAULT_SORT,
    REVENUE_SORT_FIELDS,
    build_revenue_context,
    filter_revenue_queryset,
)

CURRENCY_SYMBOL = '₱'


def _parse_decimal(raw_value):
    """Convert a form value to a Decimal, returning None when invalid."""
    try:
        value = Decimal(str(raw_value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not value.is_finite():
        return None
    return value


def _filters_from_request(request):
    """Read and validate the revenue filters from the query string."""
    farm_id = None
    raw_farm_id = request.GET.get('farm', '').strip()
    if raw_farm_id.isdigit():
        farm_id = int(raw_farm_id)

    crop_id = None
    raw_crop_id = request.GET.get('crop', '').strip()
    if raw_crop_id.isdigit():
        crop_id = int(raw_crop_id)

    sort = request.GET.get('sort', DEFAULT_SORT).strip()
    if sort not in REVENUE_SORT_FIELDS:
        sort = DEFAULT_SORT

    return {
        'query': request.GET.get('q', '').strip(),
        'farm_id': farm_id,
        'crop_id': crop_id,
        'date_from': request.GET.get('date_from', '').strip(),
        'date_to': request.GET.get('date_to', '').strip(),
        'sort': sort,
    }


def _parsed_filters(filters):
    """Convert raw filter strings into values the service can query with."""
    return {
        'query': filters['query'],
        'farm_id': filters['farm_id'],
        'crop_id': filters['crop_id'],
        'date_from': (
            parse_date(filters['date_from']) if filters['date_from'] else None
        ),
        'date_to': (
            parse_date(filters['date_to']) if filters['date_to'] else None
        ),
        'sort': filters['sort'],
    }


def _csv_value(value):
    """Render a value safely for spreadsheet applications."""
    text = '' if value is None else str(value)
    if text.startswith(('=', '+', '-', '@')):
        return f"'{text}"
    return text


def _revenue_json(revenue):
    """Serialize a revenue record to a JSON-friendly dict."""
    return {
        'id': revenue.id,
        'revenue_code': revenue.revenue_code,
        'crop_id': revenue.crop_id,
        'crop_name': revenue.crop.name,
        'farm_id': revenue.farm_id,
        'farm_name': revenue.farm.name,
        'sale_date': revenue.sale_date.isoformat() if revenue.sale_date else None,
        'quantity_sold': float(revenue.quantity_sold),
        'unit': revenue.unit,
        'price_per_unit': float(revenue.price_per_unit),
        'total_revenue': float(revenue.total_revenue),
        'area_hectares': float(revenue.area_hectares),
        'revenue_per_hectare': float(revenue.revenue_per_hectare),
        'average_price': float(revenue.average_price),
        'buyer': revenue.buyer,
        'notes': revenue.notes,
        'created_at': revenue.created_at.isoformat(),
    }


@login_required(login_url='login')
def revenue_list_page(request):
    """Render crop revenue tracking with per-hectare performance."""
    filters = _filters_from_request(request)
    context = build_revenue_context(
        request.user,
        _parsed_filters(filters),
        request.GET.get('page', 1),
    )

    params = request.GET.copy()
    params.pop('page', None)

    context.update({
        **filters,
        'farms': Farm.objects.filter(user=request.user).order_by('name'),
        'crops': Crop.objects.filter(user=request.user)
        .select_related('farm')
        .order_by('farm__name', 'name'),
        'sort_choices': [
            ('-sale_date', 'Date (newest)'),
            ('sale_date', 'Date (oldest)'),
            ('-revenue', 'Revenue (high-low)'),
            ('revenue', 'Revenue (low-high)'),
            ('-quantity', 'Quantity sold (high-low)'),
            ('quantity', 'Quantity sold (low-high)'),
            ('crop', 'Crop (A-Z)'),
            ('farm', 'Farm (A-Z)'),
        ],
        'currency_symbol': CURRENCY_SYMBOL,
        'query_string': params.urlencode(),
        'today': timezone.localdate(),
    })
    return render(request, 'revenue/list.html', context)


@login_required(login_url='login')
def revenue_analytics_page(request):
    """Render the hectare crop revenue analytics dashboard."""
    context = build_revenue_analytics_context(request.user, {
        'season': request.GET.get('season'),
        'region': request.GET.get('region', ''),
    })
    context['query_string'] = request.GET.urlencode()
    return render(request, 'revenue/analytics.html', context)


@login_required(login_url='login')
def revenue_export(request):
    """Export the filtered revenue records as a CSV file."""
    filters = _parsed_filters(_filters_from_request(request))
    queryset = filter_revenue_queryset(request.user, **filters)

    response = HttpResponse(content_type='text/csv')
    filename = f'crop_revenue_{timezone.localdate():%Y%m%d}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Revenue ID',
        'Sale Date',
        'Farm',
        'Farm ID',
        'Crop',
        'Variety',
        'Area (hectares)',
        'Quantity Sold',
        'Unit',
        'Price per Unit (PHP)',
        'Total Revenue (PHP)',
        'Revenue per Hectare (PHP)',
        'Quantity Sold per Hectare',
        'Buyer / Market',
        'Remarks',
    ])

    for record in queryset.select_related('farm', 'crop', 'crop__farm').iterator():
        writer.writerow([
            _csv_value(record.revenue_code),
            record.sale_date.isoformat() if record.sale_date else '',
            _csv_value(record.farm.name),
            _csv_value(record.farm.farm_code),
            _csv_value(record.crop.name if record.crop else ''),
            _csv_value(record.crop.variety if record.crop else ''),
            record.area_hectares,
            record.quantity_sold,
            _csv_value(record.unit),
            record.price_per_unit,
            record.total_revenue,
            record.revenue_per_hectare,
            record.quantity_per_hectare,
            _csv_value(record.buyer),
            _csv_value(record.notes),
        ])

    return response


@login_required(login_url='login')
@require_POST
def revenue_save_ajax(request):
    """Create or update a crop revenue record, returning its data as JSON."""
    revenue_id = request.POST.get('id', '').strip()

    if revenue_id:
        if not revenue_id.isdigit():
            return JsonResponse({'error': 'Invalid revenue record.'}, status=400)
        revenue = get_object_or_404(Revenue, pk=revenue_id, user=request.user)
        is_update = True
    else:
        revenue = Revenue(user=request.user)
        is_update = False

    crop_id = request.POST.get('crop_id', '').strip()
    if not crop_id:
        return JsonResponse({'error': 'Please select the crop being sold.'}, status=400)
    try:
        crop = Crop.objects.select_related('farm').get(
            pk=crop_id, user=request.user
        )
    except (Crop.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Selected crop does not exist.'}, status=400)

    sale_date_raw = request.POST.get('sale_date', '').strip()
    if sale_date_raw:
        sale_date = parse_date(sale_date_raw)
        if sale_date is None:
            return JsonResponse({'error': 'Enter a valid sale date.'}, status=400)
    else:
        sale_date = timezone.localdate()

    quantity_raw = request.POST.get('quantity_sold', '').strip()
    quantity_sold = _parse_decimal(quantity_raw)
    if quantity_sold is not None:
        try:
            quantity_sold = quantity_sold.quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            quantity_sold = None
    if quantity_sold is None or quantity_sold <= 0:
        return JsonResponse(
            {'error': 'Quantity sold must be a number greater than 0.'},
            status=400,
        )

    price_raw = request.POST.get('price_per_unit', '').strip()
    price_per_unit = _parse_decimal(price_raw)
    if price_per_unit is not None:
        try:
            price_per_unit = price_per_unit.quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            price_per_unit = None
    if price_per_unit is None or price_per_unit < 0:
        return JsonResponse(
            {'error': 'Price per unit must be a valid number (0 or greater).'},
            status=400,
        )

    unit = request.POST.get('unit', '').strip() or 'kg'
    buyer = request.POST.get('buyer', '').strip()
    notes = request.POST.get('notes', '').strip()

    revenue.crop = crop
    revenue.farm = crop.farm
    revenue.sale_date = sale_date
    revenue.quantity_sold = quantity_sold
    revenue.unit = unit
    revenue.price_per_unit = price_per_unit
    revenue.buyer = buyer
    revenue.notes = notes

    try:
        revenue.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save the revenue record due to a conflict.'},
            status=400,
        )

    action = 'updated' if is_update else 'recorded'
    messages.success(
        request,
        f'Revenue {revenue.revenue_code} for "{crop.name}" has been {action} '
        f'successfully. {CURRENCY_SYMBOL}{revenue.total_revenue:,.2f} earned '
        f'({CURRENCY_SYMBOL}{revenue.revenue_per_hectare:,.2f} per hectare).',
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Revenue record {revenue.revenue_code} saved.',
        **_revenue_json(revenue),
    })


@login_required(login_url='login')
@require_POST
def revenue_delete_ajax(request, pk):
    """Delete one of the signed-in user's revenue records."""
    revenue = get_object_or_404(Revenue, pk=pk, user=request.user)
    revenue_desc = revenue.revenue_code or str(revenue)
    revenue.delete()

    messages.success(
        request,
        f'Revenue record "{revenue_desc}" has been deleted successfully.',
    )
    return JsonResponse({
        'status': 'deleted',
        'message': f'Revenue record "{revenue_desc}" has been deleted successfully.',
    })
