"""Farm progress, crop monitoring, and impact scoring helpers.

The report looks at the user's farms from four angles:

* how far each crop has progressed through its growing cycle,
* whether harvest results are healthy (quality and damage),
* whether scheduled farm work is being completed on time, and
* whether the farm's crops are succeeding, still growing, or failing.

Those signals are combined into a transparent impact score so a farm can be
flagged as having a positive, neutral, or negative impact on production.
"""

from collections import Counter, defaultdict

from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest

POSITIVE_THRESHOLD = 20
NEGATIVE_THRESHOLD = -20
CROP_POSITIVE_THRESHOLD = 10
CROP_NEGATIVE_THRESHOLD = -10

CROP_STATUS_LABELS = {
    Crop.Status.PLANTING: 'Planted',
    Crop.Status.GROWING: 'Growing',
    Crop.Status.MATURING: 'Maturing',
    Crop.Status.READY_FOR_HARVEST: 'Ready for harvest',
    Crop.Status.HARVESTED: 'Harvested',
    Crop.Status.FAILED: 'Failed',
}

CROP_STATUS_BADGES = {
    Crop.Status.PLANTING: 'bg-info-lt text-info',
    Crop.Status.GROWING: 'bg-primary-lt text-primary',
    Crop.Status.MATURING: 'bg-warning-lt text-warning',
    Crop.Status.READY_FOR_HARVEST: 'bg-orange-lt text-orange',
    Crop.Status.HARVESTED: 'bg-success-lt text-success',
    Crop.Status.FAILED: 'bg-danger-lt text-danger',
}

CROP_STATUS_COLORS = {
    Crop.Status.PLANTING: '#0ea5e9',
    Crop.Status.GROWING: '#22c55e',
    Crop.Status.MATURING: '#f59e0b',
    Crop.Status.READY_FOR_HARVEST: '#f97316',
    Crop.Status.HARVESTED: '#6366f1',
    Crop.Status.FAILED: '#ef4444',
}

IMPACT_META = {
    'positive': {
        'key': 'positive',
        'label': 'Positive impact',
        'short_label': 'Positive',
        'badge_class': 'bg-success-lt text-success',
        'icon': 'fas fa-arrow-trend-up',
        'color': '#22c55e',
        'progress_class': 'bg-success',
    },
    'neutral': {
        'key': 'neutral',
        'label': 'Neutral impact',
        'short_label': 'Neutral',
        'badge_class': 'bg-secondary-lt text-secondary',
        'icon': 'fas fa-minus',
        'color': '#94a3b8',
        'progress_class': 'bg-primary',
    },
    'negative': {
        'key': 'negative',
        'label': 'Negative impact',
        'short_label': 'Negative',
        'badge_class': 'bg-danger-lt text-danger',
        'icon': 'fas fa-arrow-trend-down',
        'color': '#ef4444',
        'progress_class': 'bg-danger',
    },
}

QUALITY_META = {
    Harvest.QualityGrade.PREMIUM: 'bg-success-lt text-success',
    Harvest.QualityGrade.GRADE_A: 'bg-primary-lt text-primary',
    Harvest.QualityGrade.GRADE_B: 'bg-info-lt text-info',
    Harvest.QualityGrade.GRADE_C: 'bg-warning-lt text-warning',
    Harvest.QualityGrade.STANDARD: 'bg-secondary-lt text-secondary',
    Harvest.QualityGrade.FAIR: 'bg-danger-lt text-danger',
}

IMPACT_CHOICES = [
    ('positive', 'Positive impact'),
    ('neutral', 'Neutral impact'),
    ('negative', 'Negative impact'),
]


def _clamp(value, low=-100, high=100):
    return max(low, min(high, value))


def _percentage(numerator, denominator, default=0):
    if not denominator:
        return default
    return round(numerator * 100 / denominator)


def _average(values):
    values = list(values)
    if not values:
        return 0
    return sum(values) / len(values)


def _as_float(value):
    if value is None:
        return 0.0
    return float(value)


def _classify(score, positive_threshold, negative_threshold):
    if score >= positive_threshold:
        return 'positive'
    if score <= negative_threshold:
        return 'negative'
    return 'neutral'


def _impact_payload(key, score):
    return {
        'impact_key': key,
        'impact_label': IMPACT_META[key]['label'],
        'impact_short_label': IMPACT_META[key]['short_label'],
        'impact_badge_class': IMPACT_META[key]['badge_class'],
        'impact_icon': IMPACT_META[key]['icon'],
        'impact_color': IMPACT_META[key]['color'],
        'impact_progress_class': IMPACT_META[key]['progress_class'],
        'impact_score': score,
    }


def crop_progress_percent(crop, today=None):
    """Return how far a crop has advanced through its growing cycle (0-100)."""
    today = today or timezone.localdate()

    if crop.actual_harvest_date or crop.status == Crop.Status.HARVESTED:
        return 100
    if crop.status == Crop.Status.READY_FOR_HARVEST:
        return 100
    if not crop.planting_date or not crop.days_to_maturity:
        return 0

    elapsed_days = (today - crop.planting_date).days
    progress = elapsed_days * 100 / crop.days_to_maturity
    return round(_clamp(progress, 0, 100))


def _progress_label(crop):
    if crop.status == Crop.Status.FAILED:
        return 'Failed before harvest'
    if crop.actual_harvest_date or crop.status == Crop.Status.HARVESTED:
        return 'Harvest complete'
    if crop.status == Crop.Status.READY_FOR_HARVEST:
        return 'Ready for harvest'

    days = crop.days_to_harvest
    if days is None:
        return 'Harvest date not set'
    if days == 0:
        return 'Harvest due today'
    if days > 0:
        return f'{days} day{"s" if days != 1 else ""} to harvest'
    return f'{abs(days)} day{"s" if abs(days) != 1 else ""} overdue'


def _activity_stats(activities):
    activities = list(activities)
    completed = sum(
        1 for activity in activities
        if activity.status == FarmActivity.Status.COMPLETED
    )
    overdue = sum(1 for activity in activities if activity.is_overdue)
    return {
        'total': len(activities),
        'completed': completed,
        'overdue': overdue,
        'completion_rate': _percentage(completed, len(activities)),
    }


def _harvest_quantity(harvests):
    quantity = sum(_as_float(harvest.quantity_harvested) for harvest in harvests)
    damaged = sum(
        _as_float(harvest.damaged_quantity)
        for harvest in harvests
        if harvest.damaged_quantity is not None
    )
    return quantity, damaged


def _damage_rate(quantity, damaged):
    total = quantity + damaged
    if total <= 0:
        return 0.0
    return round(damaged * 100 / total, 1)


def _unit_totals(harvests):
    totals = defaultdict(float)
    for harvest in harvests:
        totals[harvest.unit or 'unit'] += _as_float(harvest.quantity_harvested)
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def _crop_impact(crop, harvest, activities, today):
    """Score one crop from its outcome, quality, damage, and farm work."""
    score = 0
    reasons = []
    activity_stats = _activity_stats(activities)

    if crop.status == Crop.Status.FAILED:
        score -= 60
        reasons.append('Crop was marked as damaged or failed')
    elif crop.actual_harvest_date or crop.status == Crop.Status.HARVESTED:
        score += 15
        reasons.append('Harvest completed')

        if harvest:
            quality_points = {
                Harvest.QualityGrade.PREMIUM: 15,
                Harvest.QualityGrade.GRADE_A: 12,
                Harvest.QualityGrade.GRADE_B: 6,
                Harvest.QualityGrade.STANDARD: 0,
                Harvest.QualityGrade.GRADE_C: -8,
                Harvest.QualityGrade.FAIR: -15,
            }.get(harvest.quality_grade, 0)
            score += quality_points
            if quality_points:
                reasons.append(
                    f'{harvest.get_quality_grade_display()} quality harvest'
                )

            quantity = _as_float(harvest.quantity_harvested)
            damaged = _as_float(harvest.damaged_quantity)
            damage_rate = _damage_rate(quantity, damaged)
            if damage_rate >= 20:
                score -= 25
                reasons.append(f'{damage_rate:.0f}% of produce damaged')
            elif damage_rate >= 5:
                score -= 10
                reasons.append(f'{damage_rate:.0f}% of produce damaged')

        if crop.expected_harvest_date and crop.actual_harvest_date:
            if crop.actual_harvest_date <= crop.expected_harvest_date:
                score += 10
                reasons.append('Harvested on or before the assigned date')
            elif (crop.actual_harvest_date - crop.expected_harvest_date).days > 7:
                score -= 5
                reasons.append('Harvest was more than a week late')
    elif crop.status == Crop.Status.READY_FOR_HARVEST:
        score += 12
        reasons.append('Ready for harvest')
    else:
        if crop.expected_harvest_date and crop.expected_harvest_date < today:
            days_overdue = (today - crop.expected_harvest_date).days
            score -= 30
            reasons.append(f'{days_overdue} day{"s" if days_overdue != 1 else ""} past the assigned harvest date')
        elif crop.maturity_status == 'approaching':
            score += 10
            reasons.append('Maturing on schedule')
        elif crop.days_since_planting is not None and crop.days_since_planting < 7:
            score += 5
            reasons.append('Recently planted')
        else:
            score += 10
            reasons.append('Growing on schedule')

    if activity_stats['overdue']:
        penalty = min(20, activity_stats['overdue'] * 8)
        score -= penalty
        reasons.append(
            f'{activity_stats["overdue"]} overdue activit'
            f'{"y" if activity_stats["overdue"] == 1 else "ies"}'
        )
    elif activity_stats['completed']:
        score += 5
        reasons.append('Scheduled work completed')

    score = round(_clamp(score))
    impact_key = _classify(
        score, CROP_POSITIVE_THRESHOLD, CROP_NEGATIVE_THRESHOLD
    )
    return score, impact_key, reasons, activity_stats


def _build_crop_row(crop, latest_harvest, activities, today):
    score, impact_key, reasons, activity_stats = _crop_impact(
        crop, latest_harvest, activities, today
    )

    latest_quality_key = (
        latest_harvest.quality_grade if latest_harvest else crop.quality
    )
    latest_quality_label = ''
    if latest_harvest:
        latest_quality_label = latest_harvest.get_quality_grade_display()
    elif crop.quality:
        latest_quality_label = crop.get_quality_display()

    quantity, damaged = _harvest_quantity(
        [latest_harvest] if latest_harvest else []
    )
    is_active = (
        not crop.actual_harvest_date
        and crop.status not in (Crop.Status.HARVESTED, Crop.Status.FAILED)
    )
    is_harvested = (
        bool(crop.actual_harvest_date)
        or crop.status == Crop.Status.HARVESTED
    )
    is_failed = crop.status == Crop.Status.FAILED

    if is_harvested:
        days_to_harvest_label = 'Harvested'
    elif is_failed:
        days_to_harvest_label = 'Crop failed'
    else:
        days_to_harvest_label = crop.days_to_harvest_label

    row = {
        'id': crop.id,
        'name': crop.name,
        'variety': crop.variety,
        'farm_id': crop.farm_id,
        'farm_name': crop.farm.name,
        'farm_code': crop.farm.farm_code,
        'status': crop.status,
        'status_label': CROP_STATUS_LABELS.get(
            crop.status, crop.get_status_display()
        ),
        'status_badge_class': CROP_STATUS_BADGES.get(
            crop.status, 'bg-secondary-lt text-secondary'
        ),
        'maturity_label': crop.maturity_label,
        'progress': crop_progress_percent(crop, today),
        'progress_label': _progress_label(crop),
        'planting_date': crop.planting_date,
        'expected_harvest_date': crop.expected_harvest_date,
        'actual_harvest_date': crop.actual_harvest_date,
        'days_since_planting': crop.days_since_planting,
        'days_to_harvest': crop.days_to_harvest,
        'days_to_harvest_label': days_to_harvest_label,
        'harvest_season': crop.harvest_season,
        'area_hectares': _as_float(crop.area_hectares),
        'is_active': is_active,
        'is_harvested': is_harvested,
        'is_failed': is_failed,
        'days_overdue': (
            (today - crop.expected_harvest_date).days
            if (
                crop.expected_harvest_date
                and crop.expected_harvest_date < today
                and not crop.actual_harvest_date
                and crop.status not in (Crop.Status.HARVESTED, Crop.Status.FAILED)
            )
            else 0
        ),
        'harvest': latest_harvest,
        'harvest_quantity': quantity,
        'harvest_damaged': damaged,
        'harvest_unit': latest_harvest.unit if latest_harvest else '',
        'harvest_quality_key': latest_quality_key,
        'harvest_quality_label': latest_quality_label,
        'harvest_quality_badge_class': QUALITY_META.get(
            latest_quality_key, 'bg-secondary-lt text-secondary'
        ),
        'activity_total': activity_stats['total'],
        'activity_completed': activity_stats['completed'],
        'activity_overdue': activity_stats['overdue'],
        'activity_completion_rate': activity_stats['completion_rate'],
        'impact_reasons': reasons,
        'impact_summary': '; '.join(reasons[:2]),
    }
    row.update(_impact_payload(impact_key, score))
    return row


def _quality_component(harvests):
    if not harvests:
        return 0
    counts = Counter(harvest.quality_grade for harvest in harvests)
    good = counts[Harvest.QualityGrade.PREMIUM] + counts[Harvest.QualityGrade.GRADE_A]
    poor = counts[Harvest.QualityGrade.FAIR]
    rated = sum(counts.values())
    if not rated:
        return 0
    return (good - poor) * 15 / rated


def _build_farm_row(farm, crop_rows, harvests, activities, today):
    active_crops = [row for row in crop_rows if row['is_active']]
    harvested_crops = [row for row in crop_rows if row['is_harvested']]
    failed_crops = [row for row in crop_rows if row['is_failed']]
    overdue_crops = [row for row in active_crops if row['days_overdue']]

    crop_progress = _percentage(
        sum(row['progress'] for row in active_crops),
        len(active_crops) * 100,
    )

    quantity, damaged = _harvest_quantity(harvests)
    damage_rate = _damage_rate(quantity, damaged)
    activity_stats = _activity_stats(activities)
    completion_rate = activity_stats['completion_rate']

    terminal_count = len(harvested_crops) + len(failed_crops)
    success_rate = _percentage(len(harvested_crops), terminal_count)

    crop_component = _average(row['impact_score'] for row in crop_rows) * 0.5
    damage_component = (
        20 - min(40, damage_rate * 2)
        if harvests
        else 0
    )
    activity_component = (
        (completion_rate - 50) / 50 * 20
        if activity_stats['total']
        else 0
    )
    success_component = (
        (success_rate - 50) / 50 * 15
        if terminal_count
        else 0
    )
    quality_component = _quality_component(harvests)

    score = round(_clamp(
        crop_component
        + damage_component
        + activity_component
        + success_component
        + quality_component
    ))
    impact_key = _classify(score, POSITIVE_THRESHOLD, NEGATIVE_THRESHOLD)

    reasons = []
    if failed_crops:
        reasons.append({
            'tone': 'bad',
            'text': f'{len(failed_crops)} failed crop{"s" if len(failed_crops) != 1 else ""}',
        })
    if overdue_crops:
        reasons.append({
            'tone': 'bad',
            'text': (
                f'{len(overdue_crops)} crop{"s" if len(overdue_crops) != 1 else ""} '
                'past the assigned harvest date'
            ),
        })
    if damage_rate >= 5:
        reasons.append({
            'tone': 'bad',
            'text': f'{damage_rate:.0f}% of harvested produce damaged',
        })
    if activity_stats['overdue']:
        reasons.append({
            'tone': 'bad',
            'text': f'{activity_stats["overdue"]} overdue activit'
                    f'{"y" if activity_stats["overdue"] == 1 else "ies"}',
        })
    if harvested_crops:
        reasons.append({
            'tone': 'good',
            'text': f'{len(harvested_crops)} crop{"s" if len(harvested_crops) != 1 else ""} harvested',
        })
    good_quality = sum(
        1 for harvest in harvests
        if harvest.quality_grade in (
            Harvest.QualityGrade.PREMIUM,
            Harvest.QualityGrade.GRADE_A,
        )
    )
    if good_quality:
        reasons.append({
            'tone': 'good',
            'text': f'{good_quality} good-quality harvest{"s" if good_quality != 1 else ""}',
        })
    if activity_stats['total'] and completion_rate >= 80:
        reasons.append({
            'tone': 'good',
            'text': f'{completion_rate}% of scheduled activities completed',
        })
    if active_crops and not overdue_crops:
        reasons.append({
            'tone': 'info',
            'text': f'{len(active_crops)} crop{"s" if len(active_crops) != 1 else ""} progressing',
        })
    if not reasons:
        reasons.append({
            'tone': 'info',
            'text': 'Not enough activity yet to judge impact',
        })

    units = _unit_totals(harvests)
    primary_unit = units[0][0] if units else ''
    primary_quantity = units[0][1] if units else 0

    row = {
        'farm': farm,
        'farm_id': farm.id,
        'farm_name': farm.name,
        'farm_code': farm.farm_code,
        'farm_status': farm.get_status_display(),
        'crop_count': len(crop_rows),
        'active_crop_count': len(active_crops),
        'harvested_crop_count': len(harvested_crops),
        'failed_crop_count': len(failed_crops),
        'overdue_crop_count': len(overdue_crops),
        'crop_progress': crop_progress,
        'harvest_count': len(harvests),
        'harvest_quantity': primary_quantity,
        'harvest_unit': primary_unit,
        'unit_count': len(units),
        'damage_rate': damage_rate,
        'damaged_quantity': damaged,
        'activity_total': activity_stats['total'],
        'activity_completed': activity_stats['completed'],
        'activity_overdue': activity_stats['overdue'],
        'activity_completion_rate': completion_rate,
        'success_rate': success_rate,
        'reasons': reasons,
        'impact_summary': '; '.join(reason['text'] for reason in reasons[:3]),
        'crop_rows': crop_rows,
        'harvests': harvests,
        'activities': activities,
    }
    row.update(_impact_payload(impact_key, score))
    return row


def _status_rows(crop_rows):
    counts = Counter(row['status'] for row in crop_rows)
    total = len(crop_rows)
    rows = []
    for value, _label in Crop.Status.choices:
        count = counts.get(value, 0)
        if not count:
            continue
        rows.append({
            'value': value,
            'label': CROP_STATUS_LABELS.get(value, _label),
            'count': count,
            'percent': _percentage(count, total),
            'color': CROP_STATUS_COLORS.get(value, '#94a3b8'),
        })
    return rows


def _farm_matches_query(farm, crop_rows, query):
    if not query:
        return True
    haystacks = [
        farm.name,
        farm.owner,
        farm.location,
        farm.farm_code,
        farm.description,
    ]
    haystacks.extend(row['name'] for row in crop_rows)
    haystacks.extend(row['variety'] for row in crop_rows)
    needle = query.lower()
    return any(needle in (value or '').lower() for value in haystacks)


def _empty_report(today):
    return {
        'today': today,
        'summary': {
            'farm_count': 0,
            'positive_farm_count': 0,
            'neutral_farm_count': 0,
            'negative_farm_count': 0,
            'total_crop_count': 0,
            'monitored_crop_count': 0,
            'harvested_crop_count': 0,
            'failed_crop_count': 0,
            'overdue_crop_count': 0,
            'average_progress': 0,
            'harvest_count': 0,
            'total_quantity': 0,
            'primary_unit': '',
            'primary_unit_total': 0,
            'damage_rate': 0,
            'activity_total': 0,
            'activity_completed': 0,
            'activity_overdue': 0,
            'activity_completion_rate': 0,
            'positive_farm_names': [],
            'negative_farm_names': [],
        },
        'farm_rows': [],
        'crop_rows': [],
        'status_rows': [],
        'progress_chart': {'labels': [], 'series': [], 'colors': [], 'impact': []},
    }


def build_farm_progress_report(user, farm_id=None, status=None, impact=None, query=''):
    """Build the farm progress report for one user.

    ``farm_id`` limits the report to one farm, ``status`` filters the crop
    monitor by crop status, ``impact`` filters farms by their impact rating,
    and ``query`` searches farm and crop details.
    """
    today = timezone.localdate()

    farms_qs = Farm.objects.filter(user=user)
    if farm_id:
        farms_qs = farms_qs.filter(pk=farm_id)
    farms = list(farms_qs.order_by('name'))
    if not farms:
        return _empty_report(today)

    farm_ids = [farm.id for farm in farms]

    crops = list(
        Crop.objects.filter(user=user, farm_id__in=farm_ids)
        .select_related('farm')
        .order_by('farm__name', 'name')
    )
    harvests = list(
        Harvest.objects.filter(user=user, farm_id__in=farm_ids)
        .select_related('farm', 'crop')
        .order_by('-harvest_date', '-created_at')
    )
    activities = list(
        FarmActivity.objects.filter(user=user, farm_id__in=farm_ids)
        .select_related('farm', 'crop')
        .order_by('scheduled_date', 'id')
    )

    harvests_by_farm = defaultdict(list)
    for harvest in harvests:
        harvests_by_farm[harvest.farm_id].append(harvest)

    activities_by_farm = defaultdict(list)
    for activity in activities:
        activities_by_farm[activity.farm_id].append(activity)

    latest_harvest_by_crop = {}
    activities_by_crop = defaultdict(list)
    for harvest in harvests:
        if harvest.crop_id:
            latest_harvest_by_crop.setdefault(harvest.crop_id, harvest)
    for activity in activities:
        if activity.crop_id:
            activities_by_crop[activity.crop_id].append(activity)

    crop_rows_by_farm = defaultdict(list)
    all_crop_rows = []
    for crop in crops:
        row = _build_crop_row(
            crop,
            latest_harvest_by_crop.get(crop.id),
            activities_by_crop.get(crop.id, []),
            today,
        )
        crop_rows_by_farm[crop.farm_id].append(row)
        all_crop_rows.append(row)

    farm_rows = [
        _build_farm_row(
            farm,
            crop_rows_by_farm.get(farm.id, []),
            harvests_by_farm.get(farm.id, []),
            activities_by_farm.get(farm.id, []),
            today,
        )
        for farm in farms
    ]

    if query:
        farm_rows = [
            row for row in farm_rows
            if _farm_matches_query(
                row['farm'], row['crop_rows'], query
            )
        ]

    if impact in IMPACT_META:
        farm_rows = [
            row for row in farm_rows if row['impact_key'] == impact
        ]

    farm_rows.sort(key=lambda row: (row['impact_score'], row['farm_name']))
    visible_farm_ids = {row['farm_id'] for row in farm_rows}

    visible_crop_rows = [
        row for row in all_crop_rows if row['farm_id'] in visible_farm_ids
    ]
    if status in CROP_STATUS_LABELS:
        visible_crop_rows = [
            row for row in visible_crop_rows if row['status'] == status
        ]
    visible_crop_rows.sort(key=lambda row: (
        row['impact_score'],
        row['progress'],
        row['farm_name'],
        row['name'],
    ))

    summary_crops = [
        row for row in all_crop_rows if row['farm_id'] in visible_farm_ids
    ]
    active_crops = [row for row in summary_crops if row['is_active']]
    harvested_crops = [row for row in summary_crops if row['is_harvested']]
    failed_crops = [row for row in summary_crops if row['is_failed']]
    overdue_crops = [
        row for row in summary_crops
        if row['is_active'] and row['days_overdue']
    ]

    visible_harvests = [
        harvest for harvest in harvests
        if harvest.farm_id in visible_farm_ids
    ]
    visible_activities = [
        activity for activity in activities
        if activity.farm_id in visible_farm_ids
    ]

    quantity, damaged = _harvest_quantity(visible_harvests)
    damage_rate = _damage_rate(quantity, damaged)
    activity_stats = _activity_stats(visible_activities)
    units = _unit_totals(visible_harvests)

    positive_farms = sorted(
        (row for row in farm_rows if row['impact_key'] == 'positive'),
        key=lambda row: row['impact_score'],
        reverse=True,
    )
    negative_farms = sorted(
        (row for row in farm_rows if row['impact_key'] == 'negative'),
        key=lambda row: row['impact_score'],
    )

    summary = {
        'farm_count': len(farm_rows),
        'positive_farm_count': len(positive_farms),
        'neutral_farm_count': sum(
            1 for row in farm_rows if row['impact_key'] == 'neutral'
        ),
        'negative_farm_count': len(negative_farms),
        'total_crop_count': len(summary_crops),
        'monitored_crop_count': len(active_crops),
        'harvested_crop_count': len(harvested_crops),
        'failed_crop_count': len(failed_crops),
        'overdue_crop_count': len(overdue_crops),
        'average_progress': _percentage(
            sum(row['progress'] for row in active_crops),
            len(active_crops) * 100,
        ),
        'harvest_count': len(visible_harvests),
        'total_quantity': quantity,
        'primary_unit': units[0][0] if units else '',
        'primary_unit_total': units[0][1] if units else 0,
        'damage_rate': damage_rate,
        'activity_total': activity_stats['total'],
        'activity_completed': activity_stats['completed'],
        'activity_overdue': activity_stats['overdue'],
        'activity_completion_rate': activity_stats['completion_rate'],
        'positive_farm_names': [row['farm_name'] for row in positive_farms],
        'negative_farm_names': [row['farm_name'] for row in negative_farms],
    }

    progress_chart = {
        'labels': [row['farm_name'] for row in farm_rows],
        'series': [row['crop_progress'] for row in farm_rows],
        'colors': [row['impact_color'] for row in farm_rows],
        'impact': [row['impact_short_label'] for row in farm_rows],
    }

    return {
        'today': today,
        'summary': summary,
        'farm_rows': farm_rows,
        'crop_rows': visible_crop_rows,
        'status_rows': _status_rows(summary_crops),
        'progress_chart': progress_chart,
    }
