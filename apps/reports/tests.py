from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest


class FarmProgressReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='report-owner',
            password='secret1234',
            first_name='Mia',
        )
        self.today = timezone.localdate()
        self.client.force_login(self.user)

        self.positive_farm = Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='North Field',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )
        self.negative_farm = Farm.objects.create(
            user=self.user,
            name='Rocky Ridge Farm',
            owner='Mia Santos',
            location='South Field',
            size_hectares=Decimal('8.00'),
            date_registered=timezone.now(),
        )

        self.harvested_crop = Crop.objects.create(
            user=self.user,
            farm=self.positive_farm,
            name='Rice',
            variety='IR64',
            planting_date=self.today - timedelta(days=90),
            days_to_maturity=90,
            area_hectares=Decimal('2.00'),
            status=Crop.Status.HARVESTED,
            actual_harvest_date=self.today,
        )
        Harvest.objects.create(
            user=self.user,
            farm=self.positive_farm,
            crop=self.harvested_crop,
            harvest_date=self.today,
            quantity_harvested=Decimal('100.00'),
            unit='kg',
            quality_grade=Harvest.QualityGrade.PREMIUM,
            damaged_quantity=Decimal('0.00'),
            workers_count=3,
            harvested_by='Mia Santos',
        )
        FarmActivity.objects.create(
            user=self.user,
            farm=self.positive_farm,
            crop=self.harvested_crop,
            activity_type=FarmActivity.ActivityType.HARVEST_PREPARATION,
            location='North Field',
            scheduled_date=self.today,
            assigned_worker='Mia Santos',
            priority=FarmActivity.Priority.HIGH,
            status=FarmActivity.Status.COMPLETED,
        )

        self.growing_crop = Crop.objects.create(
            user=self.user,
            farm=self.positive_farm,
            name='Green Onion',
            variety='Local',
            planting_date=self.today - timedelta(days=30),
            days_to_maturity=60,
            area_hectares=Decimal('1.00'),
            status=Crop.Status.GROWING,
        )

        self.failed_crop = Crop.objects.create(
            user=self.user,
            farm=self.negative_farm,
            name='Tomato',
            variety='Cherry',
            planting_date=self.today - timedelta(days=40),
            days_to_maturity=60,
            area_hectares=Decimal('1.50'),
            status=Crop.Status.FAILED,
        )
        self.fair_crop = Crop.objects.create(
            user=self.user,
            farm=self.negative_farm,
            name='Corn',
            variety='Sweet',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('3.00'),
            status=Crop.Status.HARVESTED,
            actual_harvest_date=self.today,
        )
        Harvest.objects.create(
            user=self.user,
            farm=self.negative_farm,
            crop=self.fair_crop,
            harvest_date=self.today,
            quantity_harvested=Decimal('60.00'),
            unit='kg',
            quality_grade=Harvest.QualityGrade.FAIR,
            damaged_quantity=Decimal('40.00'),
            workers_count=2,
            harvested_by='Mia Santos',
        )
        FarmActivity.objects.create(
            user=self.user,
            farm=self.negative_farm,
            crop=self.failed_crop,
            activity_type=FarmActivity.ActivityType.PEST_INSPECTION,
            location='South Field',
            scheduled_date=self.today - timedelta(days=3),
            assigned_worker='Mia Santos',
            priority=FarmActivity.Priority.URGENT,
            status=FarmActivity.Status.PENDING,
        )

        other_user = User.objects.create_user(
            username='other-report-owner',
            password='secret1234',
        )
        hidden_farm = Farm.objects.create(
            user=other_user,
            name='Hidden Farm',
            owner='Other Owner',
            location='East Field',
            size_hectares=Decimal('4.00'),
            date_registered=timezone.now(),
        )
        Crop.objects.create(
            user=other_user,
            farm=hidden_farm,
            name='Hidden Crop',
            planting_date=self.today,
            days_to_maturity=50,
            area_hectares=Decimal('1.00'),
        )

    def _farm_row(self, response, farm):
        return next(
            row for row in response.context['farm_rows']
            if row['farm_id'] == farm.id
        )

    def _crop_row(self, response, crop):
        return next(
            row for row in response.context['crop_rows']
            if row['id'] == crop.id
        )

    def test_report_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('reports:farm_progress'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_report_classifies_farm_impact(self):
        response = self.client.get(reverse('reports:farm_progress'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reports/farm_progress.html')

        positive_row = self._farm_row(response, self.positive_farm)
        negative_row = self._farm_row(response, self.negative_farm)

        self.assertEqual(positive_row['impact_key'], 'positive')
        self.assertEqual(negative_row['impact_key'], 'negative')
        self.assertGreater(positive_row['impact_score'], 0)
        self.assertLess(negative_row['impact_score'], 0)

        self.assertEqual(response.context['summary']['farm_count'], 2)
        self.assertEqual(response.context['summary']['positive_farm_count'], 1)
        self.assertEqual(response.context['summary']['negative_farm_count'], 1)
        self.assertEqual(response.context['summary']['harvested_crop_count'], 2)
        self.assertEqual(response.context['summary']['failed_crop_count'], 1)
        self.assertEqual(negative_row['damage_rate'], 40.0)
        self.assertEqual(negative_row['failed_crop_count'], 1)
        self.assertEqual(negative_row['activity_overdue'], 1)

    def test_report_is_scoped_to_the_signed_in_user(self):
        response = self.client.get(reverse('reports:farm_progress'))

        self.assertEqual(len(response.context['farm_rows']), 2)
        self.assertNotContains(response, 'Hidden Farm')
        self.assertNotContains(response, 'Hidden Crop')

    def test_crop_progress_is_calculated_from_planting_and_maturity(self):
        response = self.client.get(reverse('reports:farm_progress'))

        growing_row = self._crop_row(response, self.growing_crop)
        harvested_row = self._crop_row(response, self.harvested_crop)

        self.assertEqual(growing_row['progress'], 50)
        self.assertEqual(growing_row['progress_label'], '30 days to harvest')
        self.assertEqual(growing_row['impact_key'], 'positive')
        self.assertEqual(harvested_row['progress'], 100)
        self.assertEqual(harvested_row['progress_label'], 'Harvest complete')
        self.assertEqual(response.context['summary']['average_progress'], 50)

    def test_filters_narrow_farms_and_crops(self):
        negative_response = self.client.get(
            reverse('reports:farm_progress'), {'impact': 'negative'}
        )
        failed_response = self.client.get(
            reverse('reports:farm_progress'), {'status': 'failed'}
        )
        farm_response = self.client.get(
            reverse('reports:farm_progress'), {'farm': self.positive_farm.id}
        )

        self.assertEqual(len(negative_response.context['farm_rows']), 1)
        self.assertEqual(
            negative_response.context['farm_rows'][0]['farm_id'],
            self.negative_farm.id,
        )
        self.assertEqual(len(negative_response.context['crop_rows']), 2)

        self.assertEqual(len(failed_response.context['crop_rows']), 1)
        self.assertEqual(
            failed_response.context['crop_rows'][0]['id'],
            self.failed_crop.id,
        )

        self.assertEqual(len(farm_response.context['farm_rows']), 1)
        self.assertEqual(
            farm_response.context['farm_rows'][0]['farm_id'],
            self.positive_farm.id,
        )

    def test_csv_export_contains_crop_progress_rows(self):
        response = self.client.get(reverse('reports:farm_progress_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment;', response['Content-Disposition'])

        content = response.content.decode('utf-8-sig')
        self.assertIn('Farm,Farm ID,Crop', content)
        self.assertIn('Green Valley Farm', content)
        self.assertIn('Green Onion', content)
        self.assertIn('Positive impact', content)
        self.assertIn('Negative impact', content)
        self.assertNotIn('Hidden Farm', content)

    def test_report_renders_empty_state_without_farms(self):
        User = get_user_model()
        new_user = User.objects.create_user(
            username='no-farms',
            password='secret1234',
        )
        self.client.force_login(new_user)

        response = self.client.get(reverse('reports:farm_progress'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['farm_count'], 0)
        self.assertContains(response, 'Register a farm to start monitoring progress')
