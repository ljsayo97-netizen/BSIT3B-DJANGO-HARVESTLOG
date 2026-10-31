"""Revenue aggregation helpers for crop and per-hectare tracking."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.utils import timezone

from apps.crops.models import Crop
from apps.harvests.models import Harvest

from .models import Revenue

MONEY_PLACES = Decimal('0.01')
MONTHS_ON_CHART = 12
RECORDS_PER_PAGE = 15
TOP_CROPS_LIMIT = 8

DEFAULT_SORT = '-sale_date'
REVENUE_SORT_FIELDS = {
    '-sale_date': ('-sale_date', '-created_at'),
    'sale_date': ('sale_date', 'created_at'),
    '-revenue': ('-total_revenue', '-sale_date'),
    'revenue': ('total_revenue', 'sale_date'),
    '-quantity': ('-quantity_sold', '-sale_date'),
    'quantity': ('quantity_sold', 'sale_date'),
    'crop': ('crop__name', '-sale_date'),
    '-crop': ('-crop__name', '-sale_date'),
    'farm': ('farm__name', '-sale_date'),
    '-farm': ('-farm__name', '-sale_date'),
}


def _money(value):
    return Decimal(str(value or 0)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _divide(value, divisor):
    if not divisor:
        return _money(0)
    return _money(Decimal(str(value or 0)) / Decimal(str(divisor)))


def _percentage(value, total):
    if not total:
        return 0
    return round(float(value) * 100 / float(total))


def _month_starts(count):
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


def filter_revenue_queryset(
    user,
    *,
    query='',
    farm_id=None,
    crop_id=None,
    date_from=None,
    date_to=None,
    sort=DEFAULT_SORT,
):
    """Apply the shared search, filter, and sort options to revenue records."""
    queryset = Revenue.objects.filter(user=user).select_related(
        'farm', 'crop', 'crop__farm'
    )

    if query:
        queryset = queryset.filter(
            Q(revenue_code__icontains=query)
            | Q(crop__name__icontains=query)
            | Q(crop__variety__icontains=query)
            | Q(farm__name__icontains=query)
            | Q(buyer__icontains=query)
            | Q(notes__icontains=query)
        )

    if farm_id:
        queryset = queryset.filter(farm_id=farm_id)

    if crop_id:
        queryset = queryset.filter(crop_id=crop_id)

    if date_from:
        queryset = queryset.filter(sale_date__gte=date_from)

    if date_to:
        queryset = queryset.filter(sale_date__lte=date_to)

    order_by = REVENUE_SORT_FIELDS.get(sort, REVENUE_SORT_FIELDS[DEFAULT_SORT])
    return queryset.order_by(*order_by)


def _harvest_totals(user, crop_ids):
    """Return the harvested quantity and unit for each crop."""
    totals = {}
    if not crop_ids:
        return totals

    rows = (
        Harvest.objects.filter(user=user, crop_id__in=crop_ids)
        .values('crop_id', 'unit')
        .annotate(total=Sum('quantity_harvested'))
        .order_by('crop_id', '-total')
    )
    for row in rows:
        if row['crop_id'] in totals:
            continue
        totals[row['crop_id']] = {
            'quantity': row['total'] or Decimal('0'),
            'unit': row['unit'] or 'kg',
        }
    return totals


def _crop_matches_query(crop, query, records):
    if not query:
        return True

    needle = query.lower()
    haystacks = [
        crop.name,
        crop.variety,
        crop.farm.name,
        crop.farm.farm_code,
        crop.notes,
    ]
    if any(needle in (value or '').lower() for value in haystacks):
        return True

    return any(
        needle in (record.buyer or '').lower()
        or needle in (record.notes or '').lower()
        or needle in (record.revenue_code or '').lower()
        for record in records
    )


def build_revenue_context(user, filters, page_number=1):
    """Build the revenue dashboard, crop/hectare tracker, and sales records."""
    query = filters.get('query', '')
    farm_id = filters.get('farm_id')
    crop_id = filters.get('crop_id')
    date_from = filters.get('date_from')
    date_to = filters.get('date_to')
    sort = filters.get('sort', DEFAULT_SORT)

    revenue_qs = filter_revenue_queryset(
        user,
        query=query,
        farm_id=farm_id,
        crop_id=crop_id,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
    )
    revenue_records = list(revenue_qs)

    crops_qs = Crop.objects.filter(user=user).select_related('farm')
    if farm_id:
        crops_qs = crops_qs.filter(farm_id=farm_id)
    if crop_id:
        crops_qs = crops_qs.filter(pk=crop_id)
    crops = list(crops_qs.order_by('farm__name', 'name', '-planting_date'))

    revenue_by_crop = defaultdict(list)
    for record in revenue_records:
        revenue_by_crop[record.crop_id].append(record)

    harvest_by_crop = _harvest_totals(user, [crop.id for crop in crops])

    crop_rows = []
    for crop in crops:
        records = revenue_by_crop.get(crop.id, [])
        if not _crop_matches_query(crop, query, records):
            continue

        revenue_total = sum(
            (record.total_revenue for record in records), Decimal('0')
        )
        sold_quantity = sum(
            (record.quantity_sold for record in records), Decimal('0')
        )
        sold_units = sorted({record.unit for record in records if record.unit})
        harvest = harvest_by_crop.get(crop.id, {})
        harvested_quantity = harvest.get('quantity', Decimal('0'))
        harvest_unit = harvest.get('unit', '')
        area = crop.area_hectares or Decimal('0')
        last_sale = max(
            (record.sale_date for record in records),
            default=None,
        )

        crop_rows.append({
            'crop': crop,
            'crop_id': crop.id,
            'crop_name': crop.name,
            'variety': crop.variety,
            'farm_name': crop.farm.name,
            'farm_code': crop.farm.farm_code,
            'area_hectares': area,
            'harvested_quantity': harvested_quantity,
            'harvest_unit': harvest_unit,
            'yield_per_hectare': (
                _divide(harvested_quantity, area) if area else Decimal('0')
            ),
            'sold_quantity': sold_quantity,
            'sold_unit': sold_units[0] if len(sold_units) == 1 else (
                'mixed' if sold_units else ''
            ),
            'revenue_total': _money(revenue_total),
            'revenue_per_hectare': _divide(revenue_total, area),
            'average_price': _divide(revenue_total, sold_quantity),
            'sale_count': len(records),
            'last_sale_date': last_sale,
            'has_sales': bool(records),
        })

    crop_rows.sort(
        key=lambda row: (
            -float(row['revenue_per_hectare']),
            -float(row['revenue_total']),
            row['farm_name'],
            row['crop_name'],
        )
    )

    total_revenue = sum(
        (row['revenue_total'] for row in crop_rows), Decimal('0')
    )
    for row in crop_rows:
        row['revenue_share'] = _percentage(row['revenue_total'], total_revenue)

    tracked_area = sum(
        (row['area_hectares'] for row in crop_rows), Decimal('0')
    )
    area_with_sales = sum(
        (row['area_hectares'] for row in crop_rows if row['has_sales']),
        Decimal('0'),
    )
    total_sold_quantity = sum(
        (row['sold_quantity'] for row in crop_rows), Decimal('0')
    )
    total_harvested_quantity = sum(
        (row['harvested_quantity'] for row in crop_rows), Decimal('0')
    )

    unit_totals = []
    unit_map = defaultdict(lambda: {'quantity': Decimal('0'), 'records': 0})
    for record in revenue_records:
        unit_key = record.unit or 'unit'
        unit_map[unit_key]['quantity'] += record.quantity_sold
        unit_map[unit_key]['records'] += 1
    for unit, values in sorted(
        unit_map.items(), key=lambda item: (-item[1]['quantity'], item[0])
    ):
        unit_totals.append({
            'unit': unit,
            'quantity': values['quantity'],
            'records': values['records'],
        })

    sales_crop_count = sum(1 for row in crop_rows if row['has_sales'])
    top_crop = (
        max(crop_rows, key=lambda row: row['revenue_total'])
        if crop_rows and total_revenue
        else None
    )

    month_starts = _month_starts(MONTHS_ON_CHART)
    monthly_map = defaultdict(lambda: Decimal('0'))
    for record in revenue_records:
        if record.sale_date and record.sale_date >= month_starts[0]:
            monthly_map[record.sale_date.strftime('%Y-%m')] += record.total_revenue

    revenue_chart = {
        'labels': [month.strftime('%b %Y') for month in month_starts],
        'series': [
            float(monthly_map.get(month.strftime('%Y-%m'), Decimal('0')))
            for month in month_starts
        ],
    }

    top_crops = [
        row for row in sorted(
            crop_rows,
            key=lambda row: (-float(row['revenue_total']), row['crop_name']),
        )
        if row['revenue_total'] > 0
    ][:TOP_CROPS_LIMIT]

    paginator = Paginator(revenue_qs, RECORDS_PER_PAGE)
    revenue_page = paginator.get_page(page_number)

    summary = {
        'total_revenue': _money(total_revenue),
        'revenue_per_hectare': _divide(total_revenue, tracked_area),
        'revenue_per_sold_hectare': _divide(total_revenue, area_with_sales),
        'tracked_area': tracked_area,
        'area_with_sales': area_with_sales,
        'crop_count': len(crop_rows),
        'sales_crop_count': sales_crop_count,
        'unsold_crop_count': len(crop_rows) - sales_crop_count,
        'revenue_count': len(revenue_records),
        'sold_quantity': total_sold_quantity,
        'harvested_quantity': total_harvested_quantity,
        'unit_totals': unit_totals,
        'top_crop': top_crop,
    }

    return {
        'summary': summary,
        'crop_rows': crop_rows,
        'top_crops': top_crops,
        'revenue_records': revenue_page,
        'revenue_page': revenue_page,
        'revenue_chart': revenue_chart,
    }
