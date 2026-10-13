from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.crops.models import Crop, Harvest, Sale


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_dashboard_is_public_at_root(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_login_page_is_available_at_login_url(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)

    def test_dashboard_links_are_available_without_login(self):
        paths = (
            'dashboard',
            'crops:crop_list',
            'crops:harvest_list',
            'crops:sale_list',
            'crops:yield_report',
            'info:info_list',
            'users:user_list',
        )

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(reverse(path))
                self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_crop_harvest_revenue_and_expected_harvest_metrics(self):
        crop = Crop.objects.create(
            name='Tomato',
            variety='Roma',
            farm_name='North Farm',
            expected_harvest_date=date(2999, 5, 12),
        )
        harvest = Harvest.objects.create(
            crop=crop,
            harvest_date=date(2026, 10, 10),
            quantity=Decimal('25.000'),
            unit=Harvest.Unit.KILOGRAM,
        )
        Sale.objects.create(
            harvest=harvest,
            sold_on=date(2026, 10, 11),
            quantity=Decimal('4.000'),
            unit_price=Decimal('3.50'),
        )

        response = self.client.get(reverse('dashboard'), {
            'start_date': '2026-10-01',
            'end_date': '2026-10-31',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_crops'], 1)
        self.assertEqual(response.context['total_harvests'], 1)
        self.assertEqual(response.context['selected_quantity'], [
            {'unit': Harvest.Unit.KILOGRAM, 'quantity': Decimal('25.000')},
        ])
        self.assertEqual(response.context['total_revenue'], Decimal('14.000000'))
        self.assertEqual(list(response.context['latest_harvests']), [harvest])
        self.assertEqual(list(response.context['upcoming_harvests']), [crop])

    def test_dashboard_rejects_reversed_period_and_uses_default_range(self):
        response = self.client.get(reverse('dashboard'), {
            'start_date': '2026-10-31',
            'end_date': '2026-10-01',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['period_is_valid'])
        self.assertContains(response, 'Enter a valid date range')
