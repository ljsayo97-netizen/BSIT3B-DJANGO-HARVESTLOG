"""Farm progress and impact report views."""

import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

from .services import (
    CROP_STATUS_LABELS,
    IMPACT_CHOICES,
    IMPACT_META,
    build_farm_progress_report,
)


def _filters_from_request(request):
    """Read and validate the report filters from the query string."""
    farm_id = None
    raw_farm_id = request.GET.get('farm', '').strip()
    if raw_farm_id.isdigit():
        farm_id = int(raw_farm_id)

    status = request.GET.get('status', '').strip()
    if status not in CROP_STATUS_LABELS:
        status = ''

    impact = request.GET.get('impact', '').strip()
    if impact not in IMPACT_META:
        impact = ''

    query = request.GET.get('q', '').strip()

    return {
        'farm_id': farm_id,
        'status': status,
        'impact': impact,
        'query': query,
    }


def _csv_value(value):
    """Render a value safely for spreadsheet applications."""
    text = '' if value is None else str(value)
    if text.startswith(('=', '+', '-', '@')):
        return f"'{text}"
    return text


@login_required(login_url='login')
def farm_progress_report(request):
    """Render farm impact and crop progress monitoring for the signed-in user."""
    filters = _filters_from_request(request)
    report = build_farm_progress_report(request.user, **filters)

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'reports/farm_progress.html', {
        **report,
        **filters,
        'farms': Farm.objects.filter(user=request.user).order_by('name'),
        'status_choices': [
            (value, CROP_STATUS_LABELS[value]) for value in CROP_STATUS_LABELS
        ],
        'impact_choices': IMPACT_CHOICES,
        'query_string': params.urlencode(),
    })


@login_required(login_url='login')
def farm_progress_export(request):
    """Export the crop progress monitor (with farm impact) as a CSV file."""
    filters = _filters_from_request(request)
    report = build_farm_progress_report(request.user, **filters)

    response = HttpResponse(content_type='text/csv')
    filename = f'farm_progress_report_{timezone.localdate():%Y%m%d}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow([
        'Farm',
        'Farm ID',
        'Crop',
        'Variety',
        'Crop Status',
        'Progress (%)',
        'Progress Stage',
        'Planting Date',
        'Assigned Harvest Date',
        'Actual Harvest Date',
        'Days To Harvest',
        'Area (hectares)',
        'Harvest Season',
        'Harvest Quantity',
        'Unit',
        'Harvest Quality',
        'Damaged Quantity',
        'Activities Completed',
        'Activities Total',
        'Overdue Activities',
        'Crop Impact',
        'Crop Impact Score',
        'Farm Impact',
        'Farm Impact Score',
        'Impact Notes',
    ])

    farm_impact_by_id = {
        row['farm_id']: row for row in report['farm_rows']
    }

    for row in report['crop_rows']:
        farm_impact = farm_impact_by_id.get(row['farm_id'], {})
        writer.writerow([
            _csv_value(row['farm_name']),
            _csv_value(row['farm_code']),
            _csv_value(row['name']),
            _csv_value(row['variety']),
            _csv_value(row['status_label']),
            row['progress'],
            _csv_value(row['progress_label']),
            row['planting_date'].isoformat() if row['planting_date'] else '',
            (
                row['expected_harvest_date'].isoformat()
                if row['expected_harvest_date'] else ''
            ),
            (
                row['actual_harvest_date'].isoformat()
                if row['actual_harvest_date'] else ''
            ),
            _csv_value(row['days_to_harvest_label']),
            row['area_hectares'],
            _csv_value(row['harvest_season']),
            row['harvest_quantity'],
            _csv_value(row['harvest_unit']),
            _csv_value(row['harvest_quality_label']),
            row['harvest_damaged'],
            row['activity_completed'],
            row['activity_total'],
            row['activity_overdue'],
            _csv_value(row['impact_label']),
            row['impact_score'],
            _csv_value(farm_impact.get('impact_label', '')),
            farm_impact.get('impact_score', ''),
            _csv_value(row['impact_summary']),
        ])

    return response
