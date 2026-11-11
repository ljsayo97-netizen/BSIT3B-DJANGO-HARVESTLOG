from datetime import date, timedelta
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
        self.assertEqual(response.context['top_crops_data'][0]['name'], 'Rice')
        self.assertEqual(
            response.context['top_crops_data'][0]['farm_names'],
            'Green Valley Farm',
        )
        self.assertContains(response, 'Total Farms')
        self.assertContains(response, 'Registered Crops')
        self.assertContains(response, 'Total Harvests')
        self.assertContains(response, 'Total Farm Area')
        self.assertContains(response, 'Kabankalan City')
        self.assertContains(response, 'Western Visayas')
        self.assertEqual(response.context['total_harvested_qty'], 250.0)
        self.assertEqual(response.context['total_harvest_display'], '250 kg')
        self.assertEqual(response.context['total_revenue'], 0.0)
        self.assertEqual(response.context['total_revenue_display'], '₱0.00')
        self.assertEqual(response.context['revenue_count'], 0)
        self.assertContains(response, '250 kg')
        self.assertContains(response, '₱0.00')
        self.assertContains(response, 'No sales recorded yet')
        self.assertNotContains(response, '₱192,000')
        self.assertNotContains(response, '12.8 Tons')
        self.assertEqual(response.context['unread_notification_count'], 1)
        self.assertEqual(response.context['notification_feed'][0]['title'], 'Rice')
        self.assertTrue(response.context['notification_feed'][0]['is_new'])
        self.assertEqual(response.context['harvest_progress']['total'], 1)
        self.assertEqual(response.context['harvest_progress']['in_progress'], 1)
        self.assertEqual(response.context['harvest_progress']['completed'], 0)
        self.assertEqual(response.context['harvest_progress']['completed_percent'], 0)
        self.assertEqual(response.context['harvest_progress']['in_progress_percent'], 100)

    def test_dashboard_totals_harvest_and_revenue_accurately(self):
        farm = self._create_farm()
        crop = Crop.objects.create(
            user=self.user,
            farm=farm,
            name='Rice',
            variety='IR64',
            planting_date=self.today - timedelta(days=100),
            days_to_maturity=90,
            area_hectares=Decimal('2.00'),
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=self.today,
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('1000.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=self.today,
            location='North Field',
            crop_type='Corn',
            quantity_harvested=Decimal('2.00'),
            unit='tons',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=self.today,
            location='North Field',
            crop_type='Vegetables',
            quantity_harvested=Decimal('60.00'),
            unit='baskets',
            harvested_by='Mia Santos',
        )
        Revenue.objects.create(
            user=self.user,
            crop=crop,
            sale_date=self.today,
            quantity_sold=Decimal('100.00'),
            unit='kg',
            price_per_unit=Decimal('50.00'),
        )
        Revenue.objects.create(
            user=self.user,
            crop=crop,
            sale_date=self.today,
            quantity_sold=Decimal('50.00'),
            unit='kg',
            price_per_unit=Decimal('50.00'),
        )

        response = self.client.get(reverse('dashboard'))

        # kg and tons are combined in the primary unit; baskets stay separate.
        self.assertEqual(response.context['total_harvested_qty'], 3000.0)
        self.assertEqual(response.context['total_harvest_display'], '3,000 kg')
        self.assertEqual(response.context['total_harvest_unit'], 'kg')
        self.assertEqual(
            response.context['other_harvest_unit_display'], '60 baskets'
        )

        self.assertEqual(response.context['total_revenue'], 7500.0)
        self.assertEqual(response.context['total_revenue_display'], '₱7,500.00')
        self.assertEqual(response.context['revenue_count'], 2)

        self.assertContains(response, '3,000 kg')
        self.assertContains(response, '60 baskets')
        self.assertContains(response, '₱7,500.00')
        self.assertContains(response, '2 sale records')
        self.assertNotContains(response, '₱192,000')

    def test_dashboard_shows_only_the_top_four_crops(self):
        farm = self._create_farm()
        quantities = [100, 80, 60, 40, 20]
        for index, quantity in enumerate(quantities):
            Harvest.objects.create(
                user=self.user,
                farm=farm,
                harvest_date=self.today,
                location='North Field',
                crop_type=f'Crop {index + 1}',
                quantity_harvested=Decimal(quantity),
                unit='kg',
                harvested_by='Mia Santos',
            )

        response = self.client.get(reverse('dashboard'))

        top_crops = response.context['top_crops_data']
        self.assertEqual(len(top_crops), 4)
        self.assertEqual([crop['name'] for crop in top_crops], [
            'Crop 1', 'Crop 2', 'Crop 3', 'Crop 4',
        ])

    def test_farm_distribution_includes_damaged_harvest_quantity(self):
        farm = self._create_farm()
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=self.today,
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('90.00'),
            damaged_quantity=Decimal('10.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=self.today,
            location='North Field',
            crop_type='Corn',
            quantity_harvested=Decimal('50.00'),
            damaged_quantity=Decimal('50.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )

        response = self.client.get(reverse('dashboard'))
        distribution = response.context['farm_distribution_data']

        self.assertTrue(distribution['has_damage'])
        self.assertEqual(distribution['damaged_quantity'], 60.0)
        self.assertEqual(
            distribution['labels'],
            ['Rice', 'Corn', 'Damaged Crops'],
        )
        self.assertEqual(distribution['series'], [45, 25, 30])

        damaged_item = distribution['items'][-1]
        self.assertEqual(damaged_item['name'], 'Damaged Crops')
        self.assertEqual(damaged_item['quantity'], 60.0)
        self.assertEqual(damaged_item['percentage'], 30)
        self.assertEqual(damaged_item['color'], '#ef4444')
        self.assertNotIn('Damaged Crops', [
            item['name'] for item in response.context['top_crops_data']
        ])

        self.assertContains(response, 'Damaged Crops')
        self.assertContains(response, '60 kg damaged')

    def test_dashboard_year_filter_scopes_harvest_progress_and_distribution(self):
        farm = self._create_farm()
        current_year = timezone.localdate().year
        previous_year = current_year - 1

        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(previous_year, 6, 15),
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('100.00'),
            damaged_quantity=Decimal('10.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(current_year, 6, 15),
            location='North Field',
            crop_type='Corn',
            quantity_harvested=Decimal('50.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )

        response = self.client.get(
            f"{reverse('dashboard')}?year={previous_year}"
        )

        self.assertEqual(response.context['selected_year'], previous_year)
        self.assertEqual(
            response.context['available_years'],
            [current_year, previous_year],
        )

        progress = response.context['harvest_progress_data']
        self.assertEqual(progress['year'], previous_year)
        self.assertEqual(progress['total_actual'], 100.0)

        distribution = response.context['farm_distribution_data']
        self.assertEqual(distribution['labels'], ['Rice', 'Damaged Crops'])
        self.assertEqual(distribution['series'], [91, 9])
        self.assertEqual(distribution['damaged_quantity'], 10.0)
        self.assertEqual(response.context['top_crops_data'][0]['name'], 'Rice')
        self.assertContains(response, f'<option value="{previous_year}" selected>')

        current_response = self.client.get(reverse('dashboard'))
        self.assertEqual(current_response.context['selected_year'], current_year)
        self.assertEqual(
            current_response.context['harvest_progress_data']['total_actual'],
            50.0,
        )
        self.assertEqual(
            current_response.context['farm_distribution_data']['labels'],
            ['Corn'],
        )
        self.assertEqual(
            current_response.context['farm_distribution_data']['series'],
            [100],
        )

    def test_dashboard_year_filter_shows_empty_distribution_for_missing_year(self):
        farm = self._create_farm()
        current_year = timezone.localdate().year
        empty_year = current_year - 2

        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(current_year, 6, 15),
            location='North Field',
            crop_type='Corn',
            quantity_harvested=Decimal('50.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )

        response = self.client.get(
            f"{reverse('dashboard')}?year={empty_year}"
        )

        distribution = response.context['farm_distribution_data']
        self.assertTrue(response.context['available_years'])
        self.assertIn(empty_year, response.context['available_years'])
        self.assertEqual(distribution['items'], [])
        self.assertEqual(distribution['labels'], [])
        self.assertEqual(
            response.context['harvest_progress_data']['total_actual'],
            0,
        )
        self.assertContains(
            response,
            f'No harvested crops recorded in {empty_year}.',
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

    def test_dashboard_renders_harvest_progress_from_recorded_harvests(self):
        farm = self._create_farm()
        year = timezone.localdate().year

        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(year, 1, 10),
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('1000.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(year, 1, 20),
            location='North Field',
            crop_type='Corn',
            quantity_harvested=Decimal('2.00'),
            unit='tons',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(year, 3, 5),
            location='North Field',
            crop_type='Vegetables',
            quantity_harvested=Decimal('500.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )
        Harvest.objects.create(
            user=self.user,
            farm=farm,
            harvest_date=date(year - 1, 12, 31),
            location='North Field',
            crop_type='Rice',
            quantity_harvested=Decimal('999.00'),
            unit='kg',
            harvested_by='Mia Santos',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('harvest_progress_data', response.context)
        progress_data = response.context['harvest_progress_data']

        # X-axis: January–December (12 months)
        self.assertEqual(progress_data['year'], year)
        self.assertEqual(len(progress_data['months']), 12)
        self.assertEqual(progress_data['months'][0], 'January')
        self.assertEqual(progress_data['months'][-1], 'December')

        # Y-axis uses the primary unit of the user's harvest records
        self.assertEqual(progress_data['unit'], 'kg')

        # Actual series is built from this year's recorded harvests only
        self.assertEqual(len(progress_data['actual']), 12)
        self.assertEqual(progress_data['actual'][0], 3000.0)
        self.assertEqual(progress_data['actual'][2], 500.0)
        self.assertEqual(progress_data['total_actual'], 3500.0)
        self.assertNotIn('target', progress_data)
        self.assertNotIn('Dashed line', [c['component'] for c in progress_data['components']])

        # Component specifications
        comp_names = [c['component'] for c in progress_data['components']]
        self.assertIn('X-axis', comp_names)
        self.assertIn('Y-axis', comp_names)
        self.assertIn('Green line', comp_names)
        self.assertIn('Area fill', comp_names)

        # Template contains all required texts
        self.assertContains(response, 'Harvest Progress in This Year')
        self.assertContains(response, 'harvestProgressChart')
        self.assertContains(response, 'Green line')
        self.assertContains(response, 'Actual harvest')
        self.assertContains(response, 'Area fill')
        self.assertContains(response, 'Visualizes production progress')
        self.assertContains(response, 'January–December')
        self.assertContains(response, 'Harvest quantity (kg)')
        self.assertNotContains(response, 'Target harvest')

    def test_dashboard_renders_empty_states_for_a_new_account(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register your first farm')
        self.assertContains(response, 'No harvests recorded yet')
        self.assertContains(response, 'No crops in your pipeline yet')

    def test_dashboard_has_a_widget_that_links_to_the_harvest_calendar(self):
        response = self.client.get(reverse('dashboard'))
        calendar_url = reverse('harvest_calendar:calendar')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Harvest Calendar')
        self.assertContains(response, f'href="{calendar_url}"')
        widget = response.context['harvest_calendar_widget']
        self.assertEqual(widget['url'], calendar_url)
        self.assertEqual(widget['summary']['total_events'], 0)
        self.assertEqual(widget['agenda'], [])

        calendar_response = self.client.get(calendar_url)
        self.assertEqual(calendar_response.status_code, 200)

    def test_dashboard_calendar_widget_previews_upcoming_schedule(self):
        farm = self._create_farm()
        Crop.objects.create(
            user=self.user,
            farm=farm,
            name='Rice',
            variety='IR64',
            planting_date=self.today - timedelta(days=80),
            days_to_maturity=80,
            area_hectares=Decimal('2.00'),
            status=Crop.Status.GROWING,
        )

        response = self.client.get(reverse('dashboard'))

        widget = response.context['harvest_calendar_widget']
        self.assertGreaterEqual(widget['summary']['upcoming_harvests'], 1)
        self.assertGreaterEqual(widget['month_event_count'], 1)
        self.assertTrue(widget['agenda'])
        self.assertEqual(widget['agenda'][0]['title'], 'Rice')
        self.assertEqual(widget['agenda'][0]['date'], self.today)
        self.assertContains(response, 'Open Calendar')


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
