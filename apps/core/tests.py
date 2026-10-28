from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest, HarvestNotification


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class DashboardDataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='dashboard-owner',
            password='secret1234',
            first_name='Mia',
        )
        self.today = timezone.localdate()
        self.client.force_login(self.user)

    def _create_farm(self):
        return Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='North Field',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )

    def test_dashboard_summarizes_the_users_farm_data(self):
        self.farm = self._create_farm()
        crop = Crop.objects.create(
            user=self.user,
            farm=self.farm,
            name='Rice',
            variety='IR64',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('2.00'),
            status=Crop.Status.MATURING,
        )
        harvest = Harvest.objects.create(
            user=self.user,
            farm=self.farm,
            crop=crop,
            harvest_date=self.today,
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('250.00'),
            unit='kg',
            quality_grade=Harvest.QualityGrade.PREMIUM,
            workers_count=4,
            harvested_by='Mia Santos',
        )
        activity = FarmActivity.objects.create(
            user=self.user,
            farm=self.farm,
            crop=crop,
            activity_type=FarmActivity.ActivityType.IRRIGATION,
            location='North Field',
            scheduled_date=self.today,
            assigned_worker='Mia Santos',
            priority=FarmActivity.Priority.HIGH,
            status=FarmActivity.Status.PENDING,
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['farm_count'], 1)
        self.assertEqual(response.context['active_farm_count'], 1)
        self.assertEqual(response.context['crop_count'], 1)
        self.assertEqual(response.context['active_crop_count'], 1)
        self.assertEqual(response.context['ready_crop_count'], 1)
        self.assertEqual(response.context['harvest_count'], 1)
        self.assertEqual(response.context['this_month_harvest_count'], 1)
        self.assertEqual(response.context['primary_unit'], 'kg')
        self.assertEqual(response.context['primary_unit_total'], harvest.quantity_harvested)
        self.assertEqual(response.context['approaching_crop_count'], 0)
        self.assertEqual(response.context['upcoming_harvest_count'], 1)
        self.assertTrue(
            HarvestNotification.objects.filter(
                user=self.user,
                crop=crop,
                kind=HarvestNotification.Kind.READY,
            ).exists()
        )
        self.assertEqual(response.context['recent_harvests'][0], harvest)
        self.assertEqual(response.context['quality_rows'][0]['label'], 'Premium')
        self.assertEqual(response.context['activity_summary']['total'], 1)
        self.assertEqual(response.context['activity_summary']['due_today'], 1)
        self.assertEqual(response.context['active_activity_count'], 1)
        self.assertEqual(response.context['activity_queue'][0], activity)
        self.assertEqual(len(response.context['harvest_chart_data']['labels']), 6)
        self.assertEqual(sum(response.context['crop_chart_data']['series']), 1)
        self.assertEqual(
            response.context['harvest_chart_data']['records'][-1],
            1,
        )

    def test_dashboard_is_scoped_to_the_signed_in_user(self):
        self._create_farm()
        other_user = get_user_model().objects.create_user(
            username='other-owner',
            password='secret1234',
        )
        other_farm = Farm.objects.create(
            user=other_user,
            name='Hidden Farm',
            owner='Other Owner',
            location='South Field',
            size_hectares=Decimal('8.00'),
            date_registered=timezone.now(),
        )
        Crop.objects.create(
            user=other_user,
            farm=other_farm,
            name='Corn',
            planting_date=self.today,
            area_hectares=Decimal('1.00'),
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['farm_count'], 1)
        self.assertEqual(response.context['crop_count'], 0)
        self.assertEqual(response.context['harvest_count'], 0)
        self.assertEqual(response.context['activity_summary']['total'], 0)
        self.assertNotContains(response, 'Hidden Farm')

    def test_dashboard_renders_empty_states_for_a_new_account(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register your first farm')
        self.assertContains(response, 'No harvest activity yet')
        self.assertContains(response, 'No crops yet')
