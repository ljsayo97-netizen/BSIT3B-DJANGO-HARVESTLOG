from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

from .services import build_hectare_monitoring_context


class HectareMonitoringServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='hectare-farmer',
            password='secret1234',
        )

    def _farm(self, name, size, owner='Owner', location='Farm Location'):
        return Farm.objects.create(
            user=self.user,
            name=name,
            owner=owner,
            location=location,
            size_hectares=size,
            date_registered=timezone.now(),
            status=Farm.Status.ACTIVE,
        )

    def _crop(self, farm, name, area, status=Crop.Status.GROWING, **overrides):
        values = {
            'user': self.user,
            'farm': farm,
            'name': name,
            'area_hectares': area,
            'status': status,
            'planting_date': timezone.localdate(),
            'days_to_maturity': 90,
        }
        values.update(overrides)
        return Crop.objects.create(**values)

    def test_totals_used_available_and_utilization(self):
        farm_a = self._farm('Farm A', 100)
        farm_b = self._farm('Farm B', 200)
        self._crop(farm_a, 'Rice', 30)
        self._crop(farm_b, 'Corn', 40)

        context = build_hectare_monitoring_context(self.user)

        self.assertEqual(context['total_area'], '300')
        self.assertEqual(context['used_area'], '70')
        self.assertEqual(context['available_area'], '230')
        self.assertEqual(context['land_utilization'], '23.3')
        self.assertEqual(context['remaining_percentage'], '76.7')
        self.assertEqual(context['farm_count'], 2)
        self.assertEqual(len(context['farm_rows']), 2)

    def test_harvested_and_failed_crops_release_land(self):
        farm = self._farm('Farm A', 100)
        self._crop(farm, 'Rice', 30)
        self._crop(farm, 'Corn', 25, status=Crop.Status.HARVESTED)
        self._crop(farm, 'Tomato', 15, status=Crop.Status.FAILED)

        context = build_hectare_monitoring_context(self.user)

        self.assertEqual(context['used_area'], '30')
        self.assertEqual(context['available_area'], '70')
        self.assertEqual(context['farm_rows'][0]['utilization'], 30)
        self.assertEqual(context['crop_allocation'][0]['name'], 'Rice')

    def test_approaching_capacity_status_and_alert(self):
        farm = self._farm('Kubo', 100)
        self._crop(farm, 'Rice', 60)

        context = build_hectare_monitoring_context(self.user)

        row = context['farm_rows'][0]
        self.assertEqual(row['utilization_display'], '60.0')
        self.assertEqual(row['status_label'], 'Approaching Capacity')
        self.assertEqual(context['land_utilization_status']['key'], 'approaching')
        self.assertIn('60.0% utilized', context['land_capacity_alerts'][0]['message'])

    def test_over_capacity_when_crop_area_exceeds_farm_size(self):
        farm = self._farm('Over Farm', 100)
        self._crop(farm, 'Rice', 110)

        context = build_hectare_monitoring_context(self.user)

        row = context['farm_rows'][0]
        self.assertEqual(row['used_area'], '110')
        self.assertEqual(row['available_area'], '0')
        self.assertEqual(row['utilization'], 110)
        self.assertEqual(row['status_label'], 'Over Capacity')
        self.assertEqual(row['utilization_width'], '100.0')
        self.assertIn('exceeds the registered area by 10 ha', context['land_capacity_alerts'][0]['message'])

    def test_crop_allocation_rolls_extra_crops_into_others(self):
        farm = self._farm('Farm A', 100)
        names = ['Rice', 'Corn', 'Tomato', 'Cabbage', 'Carrot', 'Onion']
        for index, name in enumerate(names, start=1):
            self._crop(farm, name, index)

        context = build_hectare_monitoring_context(self.user)
        allocation = context['crop_allocation']

        self.assertEqual(len(allocation), 6)
        self.assertEqual(allocation[0]['name'], 'Onion')
        self.assertEqual(allocation[-1]['name'], 'Others')
        self.assertEqual(allocation[-1]['area'], '1')
        self.assertEqual(allocation[-1]['percentage'], '4.8')

    def test_quick_statistics(self):
        today = timezone.localdate()
        farm = self._farm('Farm A', 100)
        self._crop(
            farm,
            'Rice',
            10,
            variety='NSIC Rc 222',
            planting_date=today - timedelta(days=10),
            days_to_maturity=20,
        )
        self._crop(
            farm,
            'Rice',
            5,
            variety='nsic rc 222',
            planting_date=today - timedelta(days=5),
            days_to_maturity=15,
        )
        self._crop(
            farm,
            'Corn',
            10,
            variety='Pioneer 30T80',
            days_to_maturity=90,
        )
        self._crop(
            farm,
            'Tomato',
            5,
            variety='Hybrid',
            status=Crop.Status.HARVESTED,
            planting_date=today - timedelta(days=10),
            days_to_maturity=20,
        )

        context = build_hectare_monitoring_context(self.user)

        self.assertEqual(context['quick_stats']['total_crops'], 4)
        self.assertEqual(context['quick_stats']['varieties'], 3)
        self.assertEqual(context['quick_stats']['farms'], 1)
        self.assertEqual(context['quick_stats']['upcoming_harvests'], 2)

    def test_only_the_signed_in_farmers_records_are_counted(self):
        other_user = get_user_model().objects.create_user(
            username='other-farmer',
            password='secret1234',
        )
        other_farm = Farm.objects.create(
            user=other_user,
            name='Other Farm',
            owner='Other',
            location='Elsewhere',
            size_hectares=500,
            date_registered=timezone.now(),
        )
        Crop.objects.create(
            user=other_user,
            farm=other_farm,
            name='Rice',
            area_hectares=200,
            status=Crop.Status.GROWING,
            planting_date=timezone.localdate(),
            days_to_maturity=90,
        )
        self._farm('My Farm', 100)

        context = build_hectare_monitoring_context(self.user)

        self.assertEqual(context['farm_count'], 1)
        self.assertEqual(context['total_area'], '100')
        self.assertEqual(context['used_area'], '0')


class HectareMonitoringViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='hectare-viewer',
            password='secret1234',
        )

    def test_page_requires_login(self):
        response = self.client.get(reverse('hectares:hectare_monitoring'))
        self.assertEqual(response.status_code, 302)

    def test_page_renders_for_signed_in_farmer(self):
        Farm.objects.create(
            user=self.user,
            name='Sunrise Farm',
            owner='Owner',
            location='Nueva Ecija',
            size_hectares=120,
            date_registered=timezone.now(),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('hectares:hectare_monitoring'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hectare Monitoring')
        self.assertContains(response, 'Sunrise Farm')
        self.assertContains(response, '120')
        self.assertContains(response, 'Farm Utilization Overview')
        self.assertContains(response, 'Land Capacity Alerts')
        self.assertContains(response, 'Crop Land Allocation')
        self.assertContains(response, 'Quick Statistics')
