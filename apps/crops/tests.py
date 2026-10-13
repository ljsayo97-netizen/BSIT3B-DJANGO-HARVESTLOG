from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import HarvestForm, SaleForm
from .models import Crop, Harvest, Sale


class CropFeatureTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='farmer',
            password='test-password',
        )
        self.other_user = get_user_model().objects.create_user(
            username='another-farmer',
            password='test-password',
        )
        self.crop = Crop.objects.create(
            owner=self.user,
            name='Tomato',
            variety='Roma',
            farm_name='North Farm',
            farm_location='Valley',
        )
        self.harvest = Harvest.objects.create(
            crop=self.crop,
            harvest_date=date(2026, 10, 10),
            quantity=Decimal('25.000'),
            unit=Harvest.Unit.KILOGRAM,
        )
        self.client.force_login(self.user)

    def test_crop_records_are_shared_with_signed_in_users(self):
        Crop.objects.create(
            owner=self.other_user,
            name='Corn',
            variety='Sweet',
            farm_name='Other Farm',
        )

        response = self.client.get(reverse('crops:crop_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tomato')
        self.assertContains(response, 'Other Farm')

    def test_harvest_form_can_select_shared_crop_records(self):
        other_crop = Crop.objects.create(
            owner=self.other_user,
            name='Corn',
            farm_name='Other Farm',
        )

        form = HarvestForm(data={
            'crop': other_crop.pk,
            'harvest_date': '2026-10-11',
            'quantity': '10',
            'unit': Harvest.Unit.KILOGRAM,
        })

        self.assertTrue(form.is_valid())

    def test_sale_revenue_and_available_quantity_are_calculated(self):
        sale = Sale.objects.create(
            harvest=self.harvest,
            sold_on=date(2026, 10, 12),
            quantity=Decimal('5.000'),
            unit_price=Decimal('3.50'),
        )

        self.assertEqual(sale.total_revenue, Decimal('17.500000'))
        self.assertEqual(self.harvest.quantity_remaining, Decimal('20.000'))

    def test_sale_form_prevents_overselling_harvest(self):
        Sale.objects.create(
            harvest=self.harvest,
            quantity=Decimal('20.000'),
            unit_price=Decimal('1.00'),
        )
        form = SaleForm(data={
            'harvest': self.harvest.pk,
            'sold_on': '2026-10-13',
            'quantity': '6',
            'unit_price': '2.00',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('quantity', form.errors)

    def test_yield_report_filters_by_date_and_crop(self):
        Harvest.objects.create(
            crop=self.crop,
            harvest_date=date(2026, 9, 10),
            quantity=Decimal('10.000'),
            unit=Harvest.Unit.KILOGRAM,
        )

        response = self.client.get(reverse('crops:yield_report'), {
            'crop': self.crop.pk,
            'start_date': '2026-10-01',
            'end_date': '2026-10-31',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['report']), 1)
        self.assertEqual(response.context['report'][0]['quantity'], Decimal('25.000'))

    def test_dashboard_shows_harvest_quantity_and_total_revenue(self):
        Sale.objects.create(
            harvest=self.harvest,
            sold_on=date(2026, 10, 12),
            quantity=Decimal('5.000'),
            unit_price=Decimal('3.50'),
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_harvests'], 1)
        self.assertEqual(response.context['total_crops'], 1)
        self.assertEqual(response.context['selected_quantity'][0]['quantity'], Decimal('25.000'))
        self.assertEqual(response.context['total_revenue'], Decimal('17.500000'))

    def test_user_can_edit_shared_crop_records(self):
        other_crop = Crop.objects.create(
            owner=self.other_user,
            name='Corn',
            farm_name='Other Farm',
        )

        response = self.client.get(reverse('crops:crop_edit', args=[other_crop.pk]))

        self.assertEqual(response.status_code, 200)


class AnonymousCropFeatureTests(TestCase):
    def test_anonymous_user_can_create_crop_harvest_and_sale(self):
        crop_response = self.client.post(reverse('crops:crop_list'), {
            'name': 'Tomato',
            'variety': 'Roma',
            'farm_name': 'Community Farm',
        })

        self.assertEqual(crop_response.status_code, 302)
        crop = Crop.objects.get(name='Tomato')
        self.assertIsNone(crop.owner)

        harvest_response = self.client.post(reverse('crops:harvest_list'), {
            'crop': crop.pk,
            'harvest_date': '2026-10-10',
            'quantity': '25',
            'unit': Harvest.Unit.KILOGRAM,
        })

        self.assertEqual(harvest_response.status_code, 302)
        harvest = Harvest.objects.get(crop=crop)

        sale_response = self.client.post(reverse('crops:sale_list'), {
            'harvest': harvest.pk,
            'sold_on': '2026-10-12',
            'quantity': '5',
            'unit_price': '3.50',
        })

        self.assertEqual(sale_response.status_code, 302)
        self.assertTrue(Sale.objects.filter(harvest=harvest).exists())
