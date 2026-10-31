"""Tests for crop revenue tracking and per-hectare calculations."""

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.revenue.models import Revenue


def make_user(username='revenue-farmer'):
    return get_user_model().objects.create_user(
        username=username, password='secret1234'
    )


def make_farm(user, name='Green Valley Farm', **overrides):
    data = {
        'name': name,
        'owner': 'Juan Dela Cruz',
        'location': 'Cauayan, Isabela',
        'size_hectares': 5.00,
        'date_registered': timezone.now(),
        'status': 'active',
        'user': user,
    }
    data.update(overrides)
    return Farm.objects.create(**data)


def make_crop(user, farm, **overrides):
    data = {
        'farm': farm,
        'user': user,
        'name': 'Rice',
        'variety': 'IR64',
        'planting_date': timezone.localdate(),
        'days_to_maturity': 90,
        'status': Crop.Status.GROWING,
        'area_hectares': 2,
    }
    data.update(overrides)
    return Crop.objects.create(**data)


def make_harvest(user, farm, crop, **overrides):
    data = {
        'farm': farm,
        'crop': crop,
        'user': user,
        'harvest_date': timezone.localdate(),
        'location': farm.location or farm.name,
        'crop_type': crop.name,
        'quantity_harvested': 1000,
        'unit': 'kg',
        'quality_grade': Harvest.QualityGrade.STANDARD,
        'workers_count': 4,
        'harvested_by': 'Juan Dela Cruz',
    }
    data.update(overrides)
    return Harvest.objects.create(**data)


def make_revenue(user, crop, **overrides):
    data = {
        'crop': crop,
        'user': user,
        'sale_date': timezone.localdate(),
        'quantity_sold': 100,
        'unit': 'kg',
        'price_per_unit': 50,
        'buyer': 'Local market',
    }
    data.update(overrides)
    return Revenue.objects.create(**data)


class RevenueModelTests(TestCase):
    def setUp(self):
        self.user = make_user('model-owner')
        self.farm = make_farm(self.user)
        self.crop = make_crop(self.user, self.farm, area_hectares=2)

    def test_total_revenue_is_computed_from_quantity_and_price(self):
        revenue = make_revenue(
            self.user,
            self.crop,
            quantity_sold=Decimal('250.50'),
            price_per_unit=Decimal('20.00'),
        )
        self.assertEqual(revenue.total_revenue, Decimal('5010.00'))

    def test_farm_is_taken_from_the_crop(self):
        other_farm = make_farm(self.user, name='Other Farm')
        self.assertNotEqual(other_farm, self.crop.farm)
        revenue = make_revenue(self.user, self.crop)
        self.assertEqual(revenue.farm, self.crop.farm)

    def test_revenue_per_hectare_uses_the_crop_area(self):
        revenue = make_revenue(
            self.user, self.crop, quantity_sold=1000, price_per_unit=20
        )
        self.assertEqual(revenue.total_revenue, Decimal('20000.00'))
        self.assertEqual(revenue.revenue_per_hectare, Decimal('10000.00'))
        self.assertEqual(revenue.quantity_per_hectare, Decimal('500.00'))

    def test_zero_area_does_not_raise_division_error(self):
        crop = make_crop(self.user, self.farm, name='Lettuce', area_hectares=0)
        revenue = make_revenue(self.user, crop)
        self.assertEqual(revenue.revenue_per_hectare, Decimal('0.00'))
        self.assertEqual(revenue.quantity_per_hectare, Decimal('0'))

    def test_revenue_code_is_sequential_per_year(self):
        first = make_revenue(
            self.user, self.crop, sale_date=date(2026, 10, 1)
        )
        second = make_revenue(
            self.user, self.crop, sale_date=date(2026, 10, 2)
        )
        next_year = make_revenue(
            self.user, self.crop, sale_date=date(2027, 1, 5)
        )

        self.assertEqual(first.revenue_code, 'REV-2026-001')
        self.assertEqual(second.revenue_code, 'REV-2026-002')
        self.assertEqual(next_year.revenue_code, 'REV-2027-001')

    def test_sale_date_defaults_to_today(self):
        revenue = Revenue.objects.create(
            crop=self.crop,
            user=self.user,
            quantity_sold=10,
            price_per_unit=5,
        )
        self.assertEqual(revenue.sale_date, timezone.localdate())


class RevenueViewTests(TestCase):
    def setUp(self):
        self.user = make_user('view-owner')
        self.other_user = make_user('other-owner')
        self.farm = make_farm(self.user)
        self.crop = make_crop(
            self.user, self.farm, name='Rice', area_hectares=2
        )
        self.harvest = make_harvest(self.user, self.farm, self.crop)
        self.client.force_login(self.user)

    def test_revenue_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('revenue:revenue_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/?next=', response.url)

    def test_revenue_page_shows_per_hectare_summary(self):
        make_revenue(
            self.user,
            self.crop,
            quantity_sold=1000,
            price_per_unit=25,
        )

        response = self.client.get(reverse('revenue:revenue_list'))

        self.assertEqual(response.status_code, 200)
        summary = response.context['summary']
        self.assertEqual(summary['total_revenue'], Decimal('25000.00'))
        self.assertEqual(summary['tracked_area'], Decimal('2'))
        self.assertEqual(summary['revenue_per_hectare'], Decimal('12500.00'))
        self.assertContains(response, 'Revenue per Hectare')

    def test_crop_tracker_includes_unsold_crops(self):
        response = self.client.get(reverse('revenue:revenue_list'))
        rows = response.context['crop_rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['crop_name'], 'Rice')
        self.assertFalse(rows[0]['has_sales'])
        self.assertEqual(rows[0]['harvested_quantity'], Decimal('1000.00'))

    def test_save_ajax_creates_a_revenue_record(self):
        response = self.client.post(reverse('revenue:revenue_save_ajax'), {
            'crop_id': self.crop.id,
            'sale_date': '2026-10-20',
            'quantity_sold': '250.50',
            'unit': 'kg',
            'price_per_unit': '20.00',
            'buyer': 'Public market',
            'notes': 'Paid in cash',
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['total_revenue'], 5010.0)
        self.assertEqual(data['revenue_per_hectare'], 2505.0)

        revenue = Revenue.objects.get(user=self.user)
        self.assertEqual(revenue.crop, self.crop)
        self.assertEqual(revenue.farm, self.farm)
        self.assertEqual(revenue.total_revenue, Decimal('5010.00'))

    def test_save_ajax_rejects_zero_quantity(self):
        response = self.client.post(reverse('revenue:revenue_save_ajax'), {
            'crop_id': self.crop.id,
            'quantity_sold': '0',
            'price_per_unit': '20',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('greater than 0', response.json()['error'])
        self.assertFalse(Revenue.objects.exists())

    def test_save_ajax_rejects_another_users_crop(self):
        other_farm = make_farm(self.other_user, name='Other Farm')
        other_crop = make_crop(self.other_user, other_farm)

        response = self.client.post(reverse('revenue:revenue_save_ajax'), {
            'crop_id': other_crop.id,
            'quantity_sold': '10',
            'price_per_unit': '20',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('does not exist', response.json()['error'])

    def test_save_ajax_updates_an_existing_record(self):
        revenue = make_revenue(
            self.user,
            self.crop,
            quantity_sold=100,
            price_per_unit=10,
        )

        response = self.client.post(reverse('revenue:revenue_save_ajax'), {
            'id': revenue.id,
            'crop_id': self.crop.id,
            'sale_date': '2026-10-21',
            'quantity_sold': '200',
            'unit': 'kg',
            'price_per_unit': '15',
        })

        self.assertEqual(response.status_code, 200)
        revenue.refresh_from_db()
        self.assertEqual(revenue.quantity_sold, Decimal('200.00'))
        self.assertEqual(revenue.price_per_unit, Decimal('15.00'))
        self.assertEqual(revenue.total_revenue, Decimal('3000.00'))
        self.assertEqual(revenue.sale_date, date(2026, 10, 21))

    def test_delete_ajax_removes_the_users_record(self):
        revenue = make_revenue(self.user, self.crop)
        response = self.client.post(
            reverse('revenue:revenue_delete_ajax', args=[revenue.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(Revenue.objects.filter(pk=revenue.pk).exists())

    def test_delete_ajax_cannot_remove_another_users_record(self):
        other_farm = make_farm(self.other_user, name='Other Farm')
        other_crop = make_crop(self.other_user, other_farm)
        other_revenue = make_revenue(self.other_user, other_crop)

        response = self.client.post(
            reverse('revenue:revenue_delete_ajax', args=[other_revenue.id])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Revenue.objects.filter(pk=other_revenue.pk).exists())

    def test_export_contains_revenue_per_hectare(self):
        make_revenue(
            self.user,
            self.crop,
            quantity_sold=1000,
            price_per_unit=25,
        )

        response = self.client.get(reverse('revenue:revenue_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8-sig')
        self.assertIn('Revenue per Hectare (PHP)', content)
        self.assertIn('12500.00', content)
        self.assertIn('Rice', content)

    def test_filtering_by_crop_limits_the_tracker(self):
        other_crop = make_crop(
            self.user, self.farm, name='Corn', variety='Sweet'
        )
        response = self.client.get(
            reverse('revenue:revenue_list'), {'crop': other_crop.id}
        )

        rows = response.context['crop_rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['crop_name'], 'Corn')
        self.assertEqual(response.context['summary']['tracked_area'], Decimal('2'))

    def test_search_matches_buyer_without_dropping_crop_row(self):
        make_revenue(self.user, self.crop, buyer='Isabela Cooperative')
        response = self.client.get(
            reverse('revenue:revenue_list'), {'q': 'Isabela'}
        )

        self.assertEqual(len(response.context['crop_rows']), 1)
        self.assertEqual(
            response.context['crop_rows'][0]['crop_name'], 'Rice'
        )


class RevenueAnalyticsViewTests(TestCase):
    """Tests for the hectare crop revenue analytics dashboard."""

    def setUp(self):
        self.user = make_user('analytics-owner')
        self.other_user = make_user('analytics-other')

        self.north = make_farm(
            self.user,
            name='North Field',
            location='Cauayan, Isabela',
            size_hectares=10,
        )
        self.south = make_farm(
            self.user,
            name='South Field',
            location='Tarlac City, Tarlac',
            size_hectares=4,
        )
        self.rice = make_crop(
            self.user,
            self.north,
            name='Rice',
            area_hectares=2,
            planting_date=date(2026, 1, 10),
        )
        self.corn = make_crop(
            self.user,
            self.south,
            name='Corn',
            area_hectares=4,
            planting_date=date(2026, 1, 12),
        )

        make_revenue(
            self.user,
            self.rice,
            sale_date=date(2026, 2, 15),
            quantity_sold=500,
            price_per_unit=60,
        )
        make_revenue(
            self.user,
            self.corn,
            sale_date=date(2026, 11, 5),
            quantity_sold=200,
            price_per_unit=40,
        )
        make_revenue(
            self.user,
            self.rice,
            sale_date=date(2025, 2, 15),
            quantity_sold=500,
            price_per_unit=40,
        )
        make_harvest(
            self.user,
            self.north,
            self.rice,
            harvest_date=date(2026, 3, 1),
            quantity_harvested=1500,
            unit='kg',
        )
        make_harvest(
            self.user,
            self.south,
            self.corn,
            harvest_date=date(2026, 11, 10),
            quantity_harvested=2,
            unit='tons',
        )

        other_farm = make_farm(
            self.other_user,
            name='Hidden Farm',
            location='Cauayan, Isabela',
            size_hectares=25,
        )
        other_crop = make_crop(
            self.other_user,
            other_farm,
            name='Soybeans',
            area_hectares=25,
            planting_date=date(2026, 2, 1),
        )
        make_revenue(
            self.other_user,
            other_crop,
            sale_date=date(2026, 4, 1),
            quantity_sold=1000,
            price_per_unit=99,
        )

        self.client.force_login(self.user)
        self.url = reverse('revenue:revenue_analytics')

    def test_analytics_page_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/?next=', response.url)

    def test_defaults_to_latest_season_and_builds_metrics(self):
        response = self.client.get(self.url)
        context = response.context

        self.assertEqual(response.status_code, 200)
        self.assertEqual(context['selected_season'], '2026')
        self.assertEqual(context['total_revenue'], Decimal('38000.00'))
        self.assertEqual(
            context['avg_revenue_per_hectare'], Decimal('6333.33')
        )
        self.assertEqual(context['total_harvest_tons'], Decimal('3.50'))
        self.assertEqual(context['total_farm_area'], Decimal('14.00'))
        self.assertEqual(context['planted_area'], Decimal('6.00'))
        self.assertEqual(context['farm_count'], 2)
        self.assertEqual(context['revenue_count'], 2)

        metrics = {metric['key']: metric for metric in context['key_metrics']}
        self.assertEqual(metrics['harvest']['value'], '3.5 t')
        self.assertEqual(metrics['area']['detail'], '2 fields · 2 regions')

        top_fields = context['top_fields']
        self.assertEqual([field['name'] for field in top_fields], [
            'North Field',
            'South Field',
        ])
        self.assertEqual(top_fields[0]['revenue_per_hectare'], 15000.0)
        self.assertEqual(top_fields[0]['band_key'], 'high')
        self.assertEqual(top_fields[1]['revenue_per_hectare'], 2000.0)
        self.assertEqual(top_fields[1]['band_key'], 'low')
        self.assertEqual(top_fields[0]['trend_pct'], 50)
        self.assertEqual(top_fields[0]['trend_label'], 'vs 2025')

    def test_renders_analytics_sections_and_chart_payloads(self):
        response = self.client.get(self.url)
        context = response.context

        self.assertContains(response, 'Hectare Crop Revenue Analytics')
        self.assertContains(response, 'Field Revenue Density Map')
        self.assertContains(response, 'Revenue per Hectare by Crop')
        self.assertContains(response, 'Top Performing Fields')
        self.assertContains(response, 'Revenue Composition by Crop Type')
        self.assertContains(response, 'Quarterly Revenue Trend (Hectare)')
        self.assertContains(response, 'Key Metrics')
        self.assertContains(response, 'revenue-analytics.css')
        self.assertContains(response, 'data-map-action="in"')

        self.assertEqual(context['crop_bar_chart']['labels'], ['Rice', 'Corn'])
        self.assertEqual(context['crop_bar_chart']['series'], [15000.0, 2000.0])
        self.assertEqual(context['composition_chart']['series'], [30000.0, 8000.0])
        self.assertEqual(context['composition_chart']['total_display'], '₱38.0K')
        self.assertEqual(context['quarterly_chart']['series'], [
            15000.0,
            0.0,
            0.0,
            2000.0,
        ])
        self.assertEqual(context['quarterly']['rows'][0]['display'], '₱15,000')

        self.assertEqual(context['map_total_fields'], 2)
        self.assertEqual(len(context['map_fields']), 2)
        self.assertTrue(all(field['points'] for field in context['map_fields']))
        json.dumps(context['map_fields'], allow_nan=False)
        json.dumps(context['crop_bar_chart'], allow_nan=False)
        json.dumps(context['composition_chart'], allow_nan=False)
        json.dumps(context['quarterly_chart'], allow_nan=False)

    def test_all_seasons_and_region_filters(self):
        all_seasons = self.client.get(self.url, {'season': ''})
        self.assertEqual(
            all_seasons.context['total_revenue'], Decimal('58000.00')
        )
        self.assertEqual(all_seasons.context['selected_season'], '')
        self.assertEqual(all_seasons.context['revenue_count'], 3)

        region = self.client.get(
            self.url, {'season': '2026', 'region': 'Isabela'}
        )
        self.assertEqual(region.context['selected_region'], 'Isabela')
        self.assertEqual(region.context['total_revenue'], Decimal('30000.00'))
        self.assertEqual(region.context['farm_count'], 1)
        self.assertEqual(region.context['total_farm_area'], Decimal('10.00'))
        region_metrics = {
            metric['key']: metric for metric in region.context['key_metrics']
        }
        self.assertEqual(region_metrics['area']['detail'], '1 field · 1 region')
        self.assertEqual(
            [field['name'] for field in region.context['top_fields']],
            ['North Field'],
        )

    def test_invalid_filters_fall_back_to_defaults(self):
        response = self.client.get(
            self.url, {'season': '1900', 'region': 'Unknown Province'}
        )
        self.assertEqual(response.context['selected_season'], '2026')
        self.assertEqual(response.context['selected_region'], '')
        self.assertEqual(
            response.context['total_revenue'], Decimal('38000.00')
        )

    def test_other_users_records_do_not_leak_into_analytics(self):
        response = self.client.get(self.url)
        context = response.context

        self.assertNotIn(
            'Hidden Farm',
            [field['name'] for field in context['field_metrics']],
        )
        self.assertNotIn(
            'Soybeans',
            [row['name'] for row in context['composition']['rows']],
        )
        self.assertEqual(context['total_revenue'], Decimal('38000.00'))
        self.assertEqual(context['total_farm_area'], Decimal('14.00'))

    def test_empty_analytics_view_for_a_new_user(self):
        empty_user = make_user('empty-analytics-owner')
        self.client.force_login(empty_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['map_fields'], [])
        self.assertEqual(response.context['top_fields'], [])
        self.assertEqual(response.context['total_revenue'], Decimal('0.00'))
        self.assertEqual(response.context['farm_count'], 0)
        self.assertContains(response, 'No fields to map yet')
        self.assertContains(response, 'No field performance to rank yet')
        self.assertContains(response, 'No crop revenue yet')
