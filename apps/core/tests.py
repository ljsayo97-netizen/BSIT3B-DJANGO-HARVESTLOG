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
from apps.revenue.models import Revenue


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
        self.assertEqual(response.context['unread_notification_count'], 1)
        self.assertEqual(response.context['notification_feed'][0]['title'], 'Rice')
        self.assertTrue(response.context['notification_feed'][0]['is_new'])
        self.assertEqual(response.context['harvest_progress']['total'], 1)
        self.assertEqual(response.context['harvest_progress']['in_progress'], 1)
        self.assertEqual(response.context['harvest_progress']['completed'], 0)
        self.assertEqual(response.context['harvest_progress']['completed_percent'], 0)
        self.assertEqual(response.context['harvest_progress']['in_progress_percent'], 100)

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
        self.assertContains(response, 'No harvests recorded yet')
        self.assertContains(response, 'No crops in your pipeline yet')


class NotificationCenterPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='notification-owner',
            password='secret1234',
            first_name='Mia',
        )
        self.today = timezone.localdate()
        self.client.force_login(self.user)

    def _create_ready_crop(self, name='Rice'):
        farm = Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='North Field',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )
        return Crop.objects.create(
            user=self.user,
            farm=farm,
            name=name,
            variety='IR64',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('2.00'),
            status=Crop.Status.MATURING,
        )

    def test_notification_center_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('notification_center'))

        self.assertEqual(response.status_code, 302)

    def test_notification_center_renders_with_the_unified_feed(self):
        self._create_ready_crop()

        response = self.client.get(reverse('notification_center'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/notification_center.html')
        self.assertContains(response, 'Notification Center')
        self.assertContains(response, 'Mark all as read')
        self.assertContains(response, 'Rice')
        self.assertEqual(response.context['unread_notification_count'], 1)
        self.assertTrue(
            any(
                item['is_unread']
                for item in response.context['notification_items']
            )
        )

    def test_notification_center_unread_filter_hides_read_items(self):
        self._create_ready_crop()
        # The first load runs readiness sync, which files the crop alert.
        self.client.get(reverse('notification_center'))
        HarvestNotification.objects.filter(user=self.user).update(is_read=True)

        response = self.client.get(
            reverse('notification_center') + '?filter=unread'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['unread_only'])
        self.assertEqual(response.context['unread_notification_count'], 0)
        self.assertEqual(list(response.context['notification_items']), [])

    def test_notification_center_is_scoped_to_the_signed_in_user(self):
        self._create_ready_crop(name='Rice')
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
            name='Secret Corn',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('1.00'),
            status=Crop.Status.MATURING,
        )

        response = self.client.get(reverse('notification_center'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rice')
        self.assertNotContains(response, 'Secret Corn')


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='search-owner',
            password='secret1234',
        )
        self.today = timezone.localdate()
        self.client.force_login(self.user)

        self.farm = Farm.objects.create(
            user=self.user,
            name='Green Valley Farm',
            owner='Mia Santos',
            location='North Field',
            size_hectares=Decimal('12.50'),
            date_registered=timezone.now(),
        )
        self.crop = Crop.objects.create(
            user=self.user,
            farm=self.farm,
            name='Rice',
            variety='IR64',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('2.00'),
            status=Crop.Status.MATURING,
        )
        self.activity = FarmActivity.objects.create(
            user=self.user,
            farm=self.farm,
            crop=self.crop,
            activity_type=FarmActivity.ActivityType.IRRIGATION,
            location='North Field',
            scheduled_date=self.today,
            assigned_worker='Mia Santos',
            priority=FarmActivity.Priority.HIGH,
            status=FarmActivity.Status.PENDING,
        )
        self.harvest = Harvest.objects.create(
            user=self.user,
            farm=self.farm,
            crop=self.crop,
            harvest_date=self.today,
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('250.00'),
            unit='kg',
            quality_grade=Harvest.QualityGrade.PREMIUM,
            workers_count=4,
            harvested_by='Mia Santos',
        )
        self.revenue = Revenue.objects.create(
            user=self.user,
            crop=self.crop,
            farm=self.farm,
            sale_date=self.today,
            quantity_sold=Decimal('100.00'),
            unit='kg',
            price_per_unit=Decimal('50.00'),
            buyer='Local Market',
        )

    def test_global_search_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('global_search'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_blank_query_renders_the_search_prompt(self):
        response = self.client.get(reverse('global_search'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/search_results.html')
        self.assertContains(response, 'Start typing to search')
        self.assertEqual(response.context['query'], '')
        self.assertEqual(response.context['total_results'], 0)

    def test_search_finds_records_across_all_modules(self):
        response = self.client.get(reverse('global_search'), {'q': 'Green Valley'})

        self.assertEqual(response.status_code, 200)
        groups = {group['key']: group for group in response.context['search_groups']}
        self.assertEqual(set(groups), {'farms', 'crops', 'activities', 'harvests', 'revenue'})
        for key, group in groups.items():
            self.assertGreaterEqual(group['total'], 1, f'{key} should have a match')
        self.assertGreaterEqual(response.context['total_results'], 5)
        self.assertContains(response, 'Green Valley Farm')
        self.assertContains(response, 'IR64')

    def test_search_matches_record_identifiers(self):
        response = self.client.get(
            reverse('global_search'),
            {'q': self.harvest.harvest_code},
        )

        groups = {group['key']: group for group in response.context['search_groups']}
        self.assertEqual(groups['harvests']['items'][0]['title'], self.harvest.harvest_code)

    def test_search_is_scoped_to_the_signed_in_user(self):
        other_user = get_user_model().objects.create_user(
            username='other-search-owner',
            password='secret1234',
        )
        Farm.objects.create(
            user=other_user,
            name='Hidden Orchard',
            owner='Other Owner',
            location='South Field',
            size_hectares=Decimal('4.00'),
            date_registered=timezone.now(),
        )

        response = self.client.get(reverse('global_search'), {'q': 'Hidden Orchard'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_results'], 0)
        for group in response.context['search_groups']:
            self.assertEqual(group['items'], [])
            self.assertEqual(group['total'], 0)
        self.assertContains(response, 'No matches for')

    def test_topbar_search_form_targets_the_search_page(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, f'action="{reverse("global_search")}"')
        self.assertContains(response, 'name="q"')
        self.assertNotContains(response, 'onsubmit="return false;"')
