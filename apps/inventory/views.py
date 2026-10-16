"""Inventory management views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.harvests.models import Harvest
from .models import InventoryItem, InventoryTransaction


def _parse_decimal(raw_value):
    """Convert a value to a float, returning None when invalid."""
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def _inventory_item_json(item):
    """Serialize an inventory item to a JSON-friendly dict."""
    if item.quantity <= 0:
        status = 'out_of_stock'
    elif item.quantity <= item.minimum_stock_level:
        status = 'low_stock'
    else:
        status = 'in_stock'

    return {
        'id': item.id,
        'product_name': item.product_name,
        'variety': item.variety,
        'quantity': float(item.quantity),
        'unit': item.unit,
        'storage_location': item.storage_location,
        'minimum_stock_level': float(item.minimum_stock_level),
        'source_harvest_id': item.source_harvest_id,
        'source_harvest_name': str(item.source_harvest) if item.source_harvest else None,
        'status': status,
        'status_display': item.get_status_display() if item.status else (
            'Out of Stock' if status == 'out_of_stock' else
            'Low Stock' if status == 'low_stock' else
            'In Stock'
        ),
        'is_low_stock': item.is_low_stock,
        'is_out_of_stock': item.is_out_of_stock,
        'notes': item.notes,
        'created_at': item.created_at.isoformat(),
    }


@login_required(login_url='login')
def inventory_list_page(request):
    """Render the searchable, filterable, paginated inventory list."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    unit = request.GET.get('unit', '').strip()
    low_stock_only = request.GET.get('low_stock', '') == '1'

    items_list = InventoryItem.objects.filter(user=request.user).order_by('-created_at')

    if query:
        items_list = items_list.filter(
            Q(product_name__icontains=query) |
            Q(variety__icontains=query) |
            Q(storage_location__icontains=query) |
            Q(notes__icontains=query)
        )

    valid_statuses = dict(InventoryItem.Status.choices)
    if status in valid_statuses:
        items_list = items_list.filter(status=status)

    if unit:
        items_list = items_list.filter(unit=unit)

    if low_stock_only:
        items_list = items_list.filter(
            quantity__lte=models.F('minimum_stock_level'),
            quantity__gt=0,
        )

    paginator = Paginator(items_list, 10)
    page_number = request.GET.get('page', 1)
    items = paginator.get_page(page_number)

    # Summary stats from all items
    total_items = items_list.count()
    low_stock_count = items_list.filter(
        quantity__lte=models.F('minimum_stock_level'),
        quantity__gt=0,
    ).count()
    out_of_stock_count = items_list.filter(quantity__lte=0).count()
    in_stock_count = items_list.filter(
        quantity__gt=models.F('minimum_stock_level'),
    ).count()

    # Recent harvests for the Source Harvest dropdown
    recent_harvests = Harvest.objects.filter(user=request.user).order_by('-harvest_date')[:10]

    return render(request, 'inventory/list.html', {
        'items': items,
        'query': query,
        'status': status,
        'unit': unit,
        'low_stock_only': low_stock_only,
        'status_choices': InventoryItem.Status.choices,
        'unit_choices': InventoryItem.Unit.choices,
        'recent_harvests': recent_harvests,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'in_stock_count': in_stock_count,
    })


@login_required(login_url='login')
def inventory_list_ajax(request):
    """Return the signed-in user's filtered inventory items as paginated JSON."""
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    unit = request.GET.get('unit', '').strip()
    low_stock_only = request.GET.get('low_stock', '') == '1'

    items_list = InventoryItem.objects.filter(user=request.user).order_by('-created_at')

    if query:
        items_list = items_list.filter(
            Q(product_name__icontains=query) |
            Q(variety__icontains=query) |
            Q(storage_location__icontains=query) |
            Q(notes__icontains=query)
        )

    valid_statuses = dict(InventoryItem.Status.choices)
    if status in valid_statuses:
        items_list = items_list.filter(status=status)

    if unit:
        items_list = items_list.filter(unit=unit)

    if low_stock_only:
        items_list = items_list.filter(
            quantity__lte=models.F('minimum_stock_level'),
            quantity__gt=0,
        )

    paginator = Paginator(items_list, 10)
    page_number = request.GET.get('page', 1)
    items = paginator.get_page(page_number)

    return JsonResponse({
        'data': [_inventory_item_json(item) for item in items.object_list],
        'has_next': items.has_next(),
        'has_prev': items.has_previous(),
        'page': items.number,
        'pages': items.paginator.num_pages,
        'total': items.paginator.count,
    })


@login_required(login_url='login')
def inventory_get_ajax(request, pk):
    """Return one of the signed-in user's inventory items as JSON."""
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    return JsonResponse(_inventory_item_json(item))


@login_required(login_url='login')
@require_POST
def inventory_save_ajax(request):
    """Validate and create or update an inventory item."""
    item_id = request.POST.get('id', '').strip()

    if item_id:
        item = get_object_or_404(InventoryItem, pk=item_id, user=request.user)
        is_update = True
    else:
        item = InventoryItem(user=request.user)
        is_update = False

    product_name = request.POST.get('product_name', '').strip()
    variety = request.POST.get('variety', '').strip()
    quantity_raw = request.POST.get('quantity', '').strip()
    unit = request.POST.get('unit', '').strip()
    storage_location = request.POST.get('storage_location', '').strip()
    minimum_stock_raw = request.POST.get('minimum_stock_level', '0').strip()
    source_harvest_id = request.POST.get('source_harvest_id', '').strip()
    status = request.POST.get('status', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not product_name:
        return JsonResponse({'error': 'Product name is required.'}, status=400)
    if not storage_location:
        return JsonResponse({'error': 'Storage location is required.'}, status=400)

    quantity_value = _parse_decimal(quantity_raw)
    if quantity_value is None or quantity_value < 0:
        return JsonResponse(
            {'error': 'Quantity must be a valid number (0 or greater).'},
            status=400,
        )

    minimum_value = _parse_decimal(minimum_stock_raw)
    if minimum_value is None or minimum_value < 0:
        return JsonResponse(
            {'error': 'Minimum stock level must be a valid number (0 or greater).'},
            status=400,
        )

    if not unit:
        unit = 'kg'

    valid_statuses = dict(InventoryItem.Status.choices)
    if status not in valid_statuses:
        return JsonResponse({'error': 'Please select a valid status.'}, status=400)

    source_harvest = None
    if source_harvest_id:
        try:
            source_harvest = Harvest.objects.get(pk=source_harvest_id, user=request.user)
        except Harvest.DoesNotExist:
            return JsonResponse({'error': 'Selected harvest does not exist.'}, status=400)

    old_quantity = item.quantity if item.pk else 0

    item.product_name = product_name
    item.variety = variety
    item.quantity = quantity_value
    item.unit = unit
    item.storage_location = storage_location
    item.minimum_stock_level = minimum_value
    item.source_harvest = source_harvest
    item.status = status
    item.notes = notes

    try:
        item.save()
    except Exception:
        return JsonResponse(
            {'error': 'Could not save inventory item due to a conflict.'},
            status=400,
        )

    # Record transaction if quantity changed
    if is_update and quantity_value != old_quantity:
        tx_type = (
            InventoryTransaction.TransactionType.ADDITION
            if quantity_value > old_quantity
            else InventoryTransaction.TransactionType.DEDUCTION
        )
        InventoryTransaction.objects.create(
            inventory_item=item,
            transaction_type=tx_type,
            quantity=abs(quantity_value - old_quantity),
            unit=unit,
            previous_quantity=old_quantity,
            new_quantity=quantity_value,
            reason=notes or f'Stock adjusted from {old_quantity} to {quantity_value}',
            performed_by=request.user.get_full_name() or request.user.username,
            user=request.user,
        )

    messages.success(
        request,
        f'Inventory item "{item.product_name}" has been {"updated" if is_update else "added"} successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_inventory_item_json(item),
    })


@login_required(login_url='login')
@require_POST
def inventory_delete_ajax(request, pk):
    """Delete the specified signed-in user's inventory item."""
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    item_name = item.product_name
    item.delete()
    messages.success(request, f'Inventory item "{item_name}" has been deleted successfully.')
    return JsonResponse({
        'status': 'deleted',
        'message': f'Inventory item "{item_name}" has been deleted successfully.',
    })


@login_required(login_url='login')
@require_POST
def inventory_adjust_ajax(request, pk):
    """Add or deduct stock from an existing inventory item and record the transaction."""
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)

    tx_type = request.POST.get('transaction_type', '').strip()
    quantity_raw = request.POST.get('quantity', '').strip()
    reason = request.POST.get('reason', '').strip()
    performed_by = request.POST.get('performed_by', '').strip() or (
        request.user.get_full_name() or request.user.username
    )

    if tx_type not in dict(InventoryTransaction.TransactionType.choices):
        return JsonResponse({'error': 'Invalid transaction type.'}, status=400)

    quantity_value = _parse_decimal(quantity_raw)
    if quantity_value is None or quantity_value <= 0:
        return JsonResponse(
            {'error': 'Quantity must be a valid number greater than 0.'},
            status=400,
        )

    previous_quantity = item.quantity

    with db_transaction.atomic():
        if tx_type == InventoryTransaction.TransactionType.ADDITION:
            new_quantity = previous_quantity + quantity_value
        elif tx_type == InventoryTransaction.TransactionType.DEDUCTION:
            if quantity_value > previous_quantity:
                return JsonResponse(
                    {'error': f'Cannot deduct {quantity_value} {item.unit}. Only {previous_quantity} available.'},
                    status=400,
                )
            new_quantity = previous_quantity - quantity_value
        else:  # ADJUSTMENT
            new_quantity = quantity_value

        item.quantity = new_quantity
        item.save()

        InventoryTransaction.objects.create(
            inventory_item=item,
            transaction_type=tx_type,
            quantity=quantity_value,
            unit=item.unit,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reason=reason or f'{tx_type} of {quantity_value} {item.unit}',
            performed_by=performed_by,
            user=request.user,
        )

    messages.success(
        request,
        f'Stock {tx_type} of {quantity_value} {item.unit} for "{item.product_name}" recorded successfully.',
    )

    return JsonResponse({
        'status': 'success',
        **_inventory_item_json(item),
    })
