"""Advanced hectare revenue analytics.

The analytics page is built from the same revenue, crop, harvest, and farm
records used by the rest of HarvestLog. No extra analytics tables are needed:
every metric is derived live so the page always matches the recorded data.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from django.db.models import Sum
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest

from .models import Revenue


CURRENCY_SYMBOL = '₱'
MONEY_PLACES = Decimal('0.01')

# Revenue density bands used by the field map, table, and crop bars.
REVENUE_HIGH_PER_HA = Decimal('12000')
REVENUE_MEDIUM_PER_HA = Decimal('6000')

MAP_FIELD_LIMIT = 12
TOP_FIELDS_LIMIT = 8
CROP_BAR_LIMIT = 8
COMPOSITION_LIMIT = 6

KG_UNITS = {'kg', 'kgs', 'kilogram', 'kilograms'}
TON_UNITS = {'t', 'ton', 'tons', 'tonne', 'tonnes', 'metric ton', 'metric tons'}

COMPOSITION_COLORS = [
    '#22c55e',
    '#38bdf8',
    '#f59e0b',
    '#a78bfa',
    '#f472b6',
    '#14b8a6',
    '#fb7185',
]

DENSITY_BANDS = (
    {
        'key': 'high',
        'label': 'High',
        'range': '≥ ₱12,000/ha',
        'color': '#22c55e',
    },
    {
        'key': 'medium',
        'label': 'Medium',
        'range': '₱6,000–₱11,999/ha',
        'color': '#f59e0b',
    },
    {
        'key': 'low',
        'label': 'Low',
        'range': '< ₱6,000/ha',
        'color': '#ef4444',
    },
    {
        'key': 'no_data',
        'label': 'No data',
        'range': 'No recorded sales',
        'color': '#64748b',
    },
)


def _decimal(value):
    return Decimal(str(value or 0))


def _money(value):
    return _decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _ratio(numerator, denominator):
    denominator = _decimal(denominator)
    if not denominator:
        return _money(0)
    return _money(_decimal(numerator) / denominator)


def _percentage(value, total):
    total = _decimal(total)
    if not total:
        return 0
    return round(float(_decimal(value)) * 100 / float(total))


def _money_display(value, decimals=2):
    return f'{CURRENCY_SYMBOL}{_decimal(value):,.{decimals}f}'


def _compact_number(value, decimals=1):
    value = float(_decimal(value))
    if abs(value) >= 1_000_000:
        return f'{value / 1_000_000:,.{decimals}f}M'
    if abs(value) >= 1_000:
        return f'{value / 1_000:,.{decimals}f}K'
    return f'{value:,.0f}'


def _compact_money(value):
    return f'{CURRENCY_SYMBOL}{_compact_number(value)}'


def _tons_display(value):
    """Render tons without unnecessary trailing zeros."""
    amount = float(_decimal(value))
    if amount.is_integer():
        return f'{amount:,.0f}'
    return f'{amount:,.2f}'.rstrip('0').rstrip('.')


def farm_region(farm):
    """Use the last part of the farm location as its region label."""
    location = (farm.location or '').strip()
    if not location:
        return 'Unassigned'
    if ',' in location:
        return location.rsplit(',', 1)[-1].strip() or 'Unassigned'
    return location


def _density_band(revenue_per_hectare, has_data):
    if not has_data:
        return DENSITY_BANDS[-1]
    if revenue_per_hectare >= REVENUE_HIGH_PER_HA:
        return DENSITY_BANDS[0]
    if revenue_per_hectare >= REVENUE_MEDIUM_PER_HA:
        return DENSITY_BANDS[1]
    return DENSITY_BANDS[2]


def _sparkline_points(values, width=76, height=24):
    """Build compact SVG polyline points for a field revenue sparkline."""
    clean_values = [max(0.0, float(value or 0)) for value in values] or [0.0]
    if len(clean_values) == 1:
        clean_values = clean_values * 2

    highest = max(clean_values) or 1.0
    step = width / (len(clean_values) - 1)
    points = []
    for index, value in enumerate(clean_values):
        x = step * index
        y = height - 2 - (value / highest) * (height - 4)
        points.append(f'{x:.1f},{y:.1f}')
    return ' '.join(points)


def _revenue_years(user):
    years = {
        year
        for year in Revenue.objects.filter(user=user).values_list(
            'sale_date__year', flat=True
        )
        if year
    }
    return sorted(years, reverse=True)


def _harvest_tons(harvests):
    """Normalize kilogram and ton harvest records to tons."""
    total = Decimal('0')
    for harvest in harvests:
        unit = (harvest.unit or '').strip().lower()
        quantity = _decimal(harvest.quantity_harvested)
        if unit in KG_UNITS:
            total += quantity / Decimal('1000')
        elif unit in TON_UNITS:
            total += quantity
    return _money(total)


def _quarter_number(sale_date):
    return (sale_date.month - 1) // 3 + 1


def _previous_revenue_by_farm(user, farm_ids, season):
    if not season:
        return {}
    rows = (
        Revenue.objects.filter(
            user=user,
            farm_id__in=farm_ids,
            sale_date__year=int(season) - 1,
        )
        .values('farm_id')
        .annotate(total=Sum('total_revenue'))
    )
    return {
        row['farm_id']: row['total'] or Decimal('0')
        for row in rows
    }


def _crop_groups(revenues, crops_by_id):
    """Group revenue records by crop type and total distinct planted area."""
    groups = defaultdict(lambda: {
        'name': '',
        'revenue': Decimal('0'),
        'crop_ids': set(),
        'quantity': Decimal('0'),
    })

    for record in revenues:
        crop_name = record.crop.name if record.crop_id else 'Other'
        group = groups[crop_name]
        group['name'] = crop_name
        group['revenue'] += record.total_revenue
        group['quantity'] += record.quantity_sold
        if record.crop_id:
            group['crop_ids'].add(record.crop_id)

    rows = []
    for group in groups.values():
        area = sum(
            (
                _decimal(crops_by_id[crop_id].area_hectares)
                for crop_id in group['crop_ids']
                if crop_id in crops_by_id
            ),
            Decimal('0'),
        )
        revenue_per_hectare = _ratio(group['revenue'], area)
        band = _density_band(revenue_per_hectare, bool(group['revenue'] and area))
        rows.append({
            'name': group['name'],
            'revenue': _money(group['revenue']),
            'revenue_display': _money_display(group['revenue']),
            'quantity': _money(group['quantity']),
            'area': _money(area),
            'area_display': f'{float(area):,.2f} ha',
            'revenue_per_hectare': revenue_per_hectare,
            'revenue_per_hectare_display': f'{_money_display(revenue_per_hectare, 0)}/ha',
            'band_key': band['key'],
            'color': band['color'],
        })

    rows.sort(
        key=lambda row: (
            -float(row['revenue_per_hectare']),
            -float(row['revenue']),
            row['name'].lower(),
        )
    )
    return rows


def _build_crop_bar(rows):
    limited = rows[:CROP_BAR_LIMIT]
    return {
        'labels': [row['name'] for row in limited],
        'series': [float(row['revenue_per_hectare']) for row in limited],
        'colors': [row['color'] for row in limited],
        'has_data': bool(limited),
    }


def _build_composition(rows, total_revenue):
    ordered_rows = sorted(
        rows, key=lambda row: (-row['revenue'], row['name'].lower())
    )
    composition_rows = [
        {
            'name': row['name'],
            'revenue': row['revenue'],
            'revenue_display': row['revenue_display'],
            'percentage': _percentage(row['revenue'], total_revenue),
            'color': COMPOSITION_COLORS[index % len(COMPOSITION_COLORS)],
        }
        for index, row in enumerate(ordered_rows)
    ]

    if len(composition_rows) > COMPOSITION_LIMIT:
        head = composition_rows[:COMPOSITION_LIMIT - 1]
        tail = composition_rows[COMPOSITION_LIMIT - 1:]
        tail_revenue = sum((row['revenue'] for row in tail), Decimal('0'))
        head.append({
            'name': 'Other crops',
            'revenue': _money(tail_revenue),
            'revenue_display': _money_display(tail_revenue),
            'percentage': _percentage(tail_revenue, total_revenue),
            'color': COMPOSITION_COLORS[(COMPOSITION_LIMIT - 1) % len(COMPOSITION_COLORS)],
        })
        composition_rows = head

    return {
        'labels': [row['name'] for row in composition_rows],
        'series': [float(row['revenue']) for row in composition_rows],
        'colors': [row['color'] for row in composition_rows],
        'rows': composition_rows,
        'has_data': bool(composition_rows and total_revenue),
        'total_display': _compact_money(total_revenue),
    }


def _build_quarterly(revenues, crops_by_id):
    buckets = {
        1: {'revenue': Decimal('0'), 'crop_ids': set()},
        2: {'revenue': Decimal('0'), 'crop_ids': set()},
        3: {'revenue': Decimal('0'), 'crop_ids': set()},
        4: {'revenue': Decimal('0'), 'crop_ids': set()},
    }
    for record in revenues:
        bucket = buckets[_quarter_number(record.sale_date)]
        bucket['revenue'] += record.total_revenue
        if record.crop_id:
            bucket['crop_ids'].add(record.crop_id)

    series = []
    revenue_series = []
    for quarter in range(1, 5):
        bucket = buckets[quarter]
        area = sum(
            (
                _decimal(crops_by_id[crop_id].area_hectares)
                for crop_id in bucket['crop_ids']
                if crop_id in crops_by_id
            ),
            Decimal('0'),
        )
        series.append(float(_ratio(bucket['revenue'], area)))
        revenue_series.append(float(bucket['revenue']))

    rows = [
        {
            'label': label,
            'value': value,
            'display': _money_display(value, 0),
        }
        for label, value in zip(['Q1', 'Q2', 'Q3', 'Q4'], series)
    ]

    return {
        'labels': ['Q1', 'Q2', 'Q3', 'Q4'],
        'series': series,
        'rows': rows,
        'revenue_series': revenue_series,
        'has_data': any(series) or any(revenue_series),
    }


def _build_field_metrics(
    farms,
    crops_by_farm,
    revenues_by_farm,
    previous_revenue_by_farm,
    avg_revenue_per_hectare,
    season,
):
    metrics = []
    for farm in farms:
        farm_crops = crops_by_farm.get(farm.id, [])
        farm_revenues = revenues_by_farm.get(farm.id, [])

        crop_area = sum(
            (_decimal(crop.area_hectares) for crop in farm_crops),
            Decimal('0'),
        )
        area = crop_area or _decimal(farm.size_hectares)
        revenue = sum(
            (record.total_revenue for record in farm_revenues),
            Decimal('0'),
        )
        revenue_per_hectare = _ratio(revenue, area)

        crop_revenue = defaultdict(lambda: Decimal('0'))
        for record in farm_revenues:
            crop_name = record.crop.name if record.crop_id else 'Other'
            crop_revenue[crop_name] += record.total_revenue
        ordered_crops = sorted(
            crop_revenue.items(), key=lambda item: (-item[1], item[0].lower())
        )
        if ordered_crops:
            top_crop = ordered_crops[0][0]
            extra_crops = len(ordered_crops) - 1
            crop_label = top_crop + (f' +{extra_crops}' if extra_crops else '')
        elif farm_crops:
            crop_label = farm_crops[0].name
        else:
            crop_label = 'No crops recorded'

        quarters = [Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0')]
        for record in farm_revenues:
            quarters[_quarter_number(record.sale_date) - 1] += record.total_revenue
        quarter_density = [_ratio(value, area) for value in quarters]

        previous_revenue = previous_revenue_by_farm.get(farm.id, Decimal('0'))
        previous_per_hectare = _ratio(previous_revenue, area)
        if previous_per_hectare:
            trend_pct = round(
                (float(revenue_per_hectare) - float(previous_per_hectare))
                * 100
                / float(previous_per_hectare)
            )
            trend_label = f'vs {int(season) - 1}' if season else 'vs previous'
        elif revenue and avg_revenue_per_hectare:
            trend_pct = round(
                (float(revenue_per_hectare) - float(avg_revenue_per_hectare))
                * 100
                / float(avg_revenue_per_hectare)
            )
            trend_label = 'vs average'
        else:
            trend_pct = None
            trend_label = ''

        if trend_pct is None:
            trend_direction = 'none'
        elif trend_pct > 0:
            trend_direction = 'up'
        elif trend_pct < 0:
            trend_direction = 'down'
        else:
            trend_direction = 'flat'

        band = _density_band(
            revenue_per_hectare,
            bool(revenue and area),
        )
        metrics.append({
            'key': f'field-{farm.id}',
            'farm_id': farm.id,
            'name': farm.name,
            'field_id': farm.farm_code or f'FARM-{farm.pk:04d}',
            'area_id': f'AREA-{farm.pk:04d}',
            'region': farm_region(farm),
            'location': farm.location,
            'crop': crop_label,
            'crop_count': len(crop_revenue),
            'area': float(area),
            'area_display': f'{float(area):,.2f}',
            'revenue': float(_money(revenue)),
            'revenue_display': _money_display(revenue),
            'revenue_per_hectare': float(revenue_per_hectare),
            'revenue_per_hectare_display': (
                f'{_money_display(revenue_per_hectare, 0)}/ha'
            ),
            'band_key': band['key'],
            'band_label': band['label'],
            'color': band['color'],
            'spark_points': _sparkline_points(quarter_density),
            'trend_pct': trend_pct,
            'trend_label': trend_label,
            'trend_direction': trend_direction,
        })

    metrics.sort(
        key=lambda row: (
            -float(row['revenue_per_hectare']),
            -float(row['revenue']),
            row['name'].lower(),
        )
    )
    return metrics


def _build_map_fields(field_metrics):
    """Lay fields out as irregular SVG plots for the density map."""
    fields = sorted(field_metrics, key=lambda row: row['name'].lower())[:MAP_FIELD_LIMIT]
    if not fields:
        return [], 420

    columns = 3 if len(fields) <= 6 else 4
    rows = max(1, ceil(len(fields) / columns))
    cell_width = 1000 / columns
    cell_height = max(180, min(250, 500 / rows))
    top_offset = 96
    view_height = top_offset + rows * cell_height + 12

    map_fields = []
    for index, field in enumerate(fields):
        column = index % columns
        row = index // columns
        x = column * cell_width + 22
        y = top_offset + row * cell_height + 10
        width = cell_width - 44
        height = cell_height - 28

        jitter = (field['farm_id'] * 7) % 11
        jitter_two = (field['farm_id'] * 13) % 9
        points = ' '.join([
            f'{x + 6 + jitter:.1f},{y + 8:.1f}',
            f'{x + width - 10:.1f},{y + 4 + jitter_two:.1f}',
            f'{x + width - 4:.1f},{y + height - 8:.1f}',
            f'{x + 10:.1f},{y + height - 2 - jitter:.1f}',
        ])
        center_x = x + width / 2
        center_y = y + height / 2

        map_fields.append({
            **field,
            'points': points,
            'label_x': round(center_x, 1),
            'label_y': round(center_y - 16, 1),
            'sub_label_y': round(center_y + 2, 1),
            'value_label_y': round(center_y + 20, 1),
        })

    return map_fields, round(view_height)


def build_revenue_analytics_context(user, filters):
    """Build the hectare revenue analytics page from live farm records."""
    years = _revenue_years(user)
    year_values = [str(year) for year in years]
    season_options = [{'value': '', 'label': 'All seasons'}] + [
        {'value': str(year), 'label': str(year)} for year in years
    ]

    raw_season = filters.get('season')
    if raw_season is None:
        selected_season = year_values[0] if year_values else ''
    elif raw_season == '':
        selected_season = ''
    elif raw_season in year_values:
        selected_season = raw_season
    else:
        selected_season = year_values[0] if year_values else ''

    all_farms = list(Farm.objects.filter(user=user).order_by('name'))
    region_map = {farm.id: farm_region(farm) for farm in all_farms}
    regions = sorted(set(region_map.values()))
    region_options = [{'value': '', 'label': 'All regions'}] + [
        {'value': region, 'label': region} for region in regions
    ]

    raw_region = (filters.get('region') or '').strip()
    selected_region = raw_region if raw_region in regions else ''

    farms = [
        farm
        for farm in all_farms
        if not selected_region or region_map[farm.id] == selected_region
    ]
    farm_ids = [farm.id for farm in farms]

    crops = list(
        Crop.objects.filter(user=user, farm_id__in=farm_ids)
        .select_related('farm')
        .order_by('farm__name', 'name')
    )
    crops_by_id = {crop.id: crop for crop in crops}

    revenues_qs = Revenue.objects.filter(
        user=user, farm_id__in=farm_ids
    ).select_related('crop', 'farm')
    harvests_qs = Harvest.objects.filter(user=user, farm_id__in=farm_ids)
    if selected_season:
        revenues_qs = revenues_qs.filter(sale_date__year=int(selected_season))
        harvests_qs = harvests_qs.filter(
            harvest_date__year=int(selected_season)
        )

    revenues = list(revenues_qs.order_by('sale_date', 'id'))
    harvests = list(harvests_qs)

    revenues_by_farm = defaultdict(list)
    for record in revenues:
        revenues_by_farm[record.farm_id].append(record)

    crops_by_farm = defaultdict(list)
    for crop in crops:
        crops_by_farm[crop.farm_id].append(crop)

    total_revenue = sum(
        (record.total_revenue for record in revenues), Decimal('0')
    )
    total_farm_area = sum(
        (_decimal(farm.size_hectares) for farm in farms), Decimal('0')
    )
    planted_area = sum(
        (_decimal(crop.area_hectares) for crop in crops), Decimal('0')
    )
    area_base = planted_area or total_farm_area
    avg_revenue_per_hectare = _ratio(total_revenue, area_base)
    total_harvest_tons = _harvest_tons(harvests)

    previous_revenue = _previous_revenue_by_farm(
        user, farm_ids, selected_season
    )
    field_metrics = _build_field_metrics(
        farms,
        crops_by_farm,
        revenues_by_farm,
        previous_revenue,
        avg_revenue_per_hectare,
        selected_season,
    )
    map_fields, map_view_height = _build_map_fields(field_metrics)

    crop_rows = _crop_groups(revenues, crops_by_id)
    crop_bar_data = _build_crop_bar(crop_rows)
    composition = _build_composition(crop_rows, total_revenue)
    quarterly = _build_quarterly(revenues, crops_by_id)

    region_count = 1 if selected_region else len(regions)
    key_metrics = [
        {
            'key': 'revenue',
            'label': 'Total Revenue',
            'value': _compact_money(total_revenue),
            'detail': _money_display(total_revenue),
            'icon': 'fas fa-sack-dollar',
            'tone': 'green',
        },
        {
            'key': 'avg_rev_ha',
            'label': 'Avg Rev/Ha',
            'value': f'{_money_display(avg_revenue_per_hectare, 0)}/ha',
            'detail': f'across {float(area_base):,.0f} planted hectares',
            'icon': 'fas fa-chart-line',
            'tone': 'blue',
        },
        {
            'key': 'harvest',
            'label': 'Total Harvest',
            'value': f'{_tons_display(total_harvest_tons)} t',
            'detail': f'{len(harvests)} harvest record'
                      f'{"s" if len(harvests) != 1 else ""}',
            'icon': 'fas fa-wheat-awn',
            'tone': 'amber',
        },
        {
            'key': 'area',
            'label': 'Total Farm Area',
            'value': f'{float(total_farm_area):,.0f} ha',
            'detail': f'{len(farms)} field{"s" if len(farms) != 1 else ""}'
                      f' · {region_count} region'
                      f'{"s" if region_count != 1 else ""}',
            'icon': 'fas fa-border-all',
            'tone': 'purple',
        },
    ]

    selected_season_label = (
        next(
            (
                option['label']
                for option in season_options
                if option['value'] == selected_season
            ),
            'All seasons',
        )
    )
    selected_region_label = selected_region or 'All regions'

    crop_bar_chart = {
        'labels': crop_bar_data['labels'],
        'series': crop_bar_data['series'],
        'colors': crop_bar_data['colors'],
    }
    composition_chart = {
        'labels': composition['labels'],
        'series': composition['series'],
        'colors': composition['colors'],
        'total_display': composition['total_display'],
    }
    quarterly_chart = {
        'labels': quarterly['labels'],
        'series': quarterly['series'],
    }

    return {
        'season_options': season_options,
        'region_options': region_options,
        'selected_season': selected_season,
        'selected_region': selected_region,
        'selected_season_label': selected_season_label,
        'selected_region_label': selected_region_label,
        'field_metrics': field_metrics,
        'map_fields': map_fields,
        'map_view_height': map_view_height,
        'map_total_fields': len(field_metrics),
        'map_field_limit': MAP_FIELD_LIMIT,
        'top_fields': field_metrics[:TOP_FIELDS_LIMIT],
        'density_bands': DENSITY_BANDS,
        'crop_bar_data': crop_bar_data,
        'crop_bar_chart': crop_bar_chart,
        'composition': composition,
        'composition_chart': composition_chart,
        'quarterly': quarterly,
        'quarterly_chart': quarterly_chart,
        'quarterly_label': selected_season_label,
        'key_metrics': key_metrics,
        'total_revenue': _money(total_revenue),
        'total_revenue_display': _money_display(total_revenue),
        'total_revenue_compact': _compact_money(total_revenue),
        'avg_revenue_per_hectare': avg_revenue_per_hectare,
        'avg_revenue_per_hectare_display': _money_display(
            avg_revenue_per_hectare, 2
        ),
        'total_harvest_tons': total_harvest_tons,
        'total_harvest_display': _tons_display(total_harvest_tons),
        'total_farm_area': _money(total_farm_area),
        'total_farm_area_display': f'{float(total_farm_area):,.2f}',
        'planted_area': _money(planted_area),
        'planted_area_display': f'{float(planted_area):,.2f}',
        'revenue_count': len(revenues),
        'farm_count': len(farms),
        'crop_type_count': len(crop_rows),
        'currency_symbol': CURRENCY_SYMBOL,
        'today': timezone.localdate(),
    }
