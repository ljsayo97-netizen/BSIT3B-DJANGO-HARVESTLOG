"""Tests for crop-driven harvests, readiness, and notifications."""

import re
from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest, HarvestNotification
from apps.harvests.services import (
    evaluate_crop,
    get_harvest_board,
    get_upcoming_harvests,
    reopen_crop_notifications,
    resolve_crop_notifications,
    sync_harvest_readiness,
)
from apps.harvests.views import (
    harvest_history_page,
    harvest_list_page,
    harvest_quality_save_ajax,
)


def make_user(username='farmer'):
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
    today = timezone.localdate()
    data = {
        'farm': farm,
        'user': user,
        'name': 'Rice',
        'variety': 'IR64',
        'planting_date': today,
        'days_to_maturity': 90,
        'status': Crop.Status.GROWING,
        'area_hectares': 2,
    }
    data.update(overrides)
    return Crop.objects.create(**data)


def make_harvest(user, farm, **overrides):
    data = {
        'farm': farm,
        'user': user,
        'harvest_date': timezone.localdate(),
        'location': farm.location or farm.name,
        'crop_type': 'Rice',
        'quantity_harvested': 1000,
        'unit': 'kg',
        'quality_grade': Harvest.QualityGrade.STANDARD,
        'workers_count': 4,
        'harvested_by': 'Juan Dela Cruz',
    }
    data.update(overrides)
    return Harvest.objects.create(**data)


class HarvestModelTests(TestCase):
    def setUp(self):
        self.user = make_user('modeluser')
        self.farm = make_farm(self.user, 'Sunny Fields')

    def test_harvest_str(self):
        harvest = make_harvest(self.user, self.farm, crop_type='Rice')
        self.assertIn('Rice', str(harvest))
        self.assertIn(harvest.harvest_code, str(harvest))

    def test_quality_choices(self):
        labels = dict(Harvest.QualityGrade.choices)
        self.assertEqual(labels['premium'], 'Premium')
        self.assertEqual(labels['grade_a'], 'Grade A')
        self.assertEqual(labels['grade_b'], 'Grade B')
        self.assertEqual(labels['grade_c'], 'Grade C')
        self.assertEqual(labels['standard'], 'Standard')
        self.assertEqual(labels['fair'], 'Fair')

    def test_harvest_code_is_sequential_per_year(self):
        first = make_harvest(
            self.user, self.farm, harvest_date=date(2026, 10, 20)
        )
        second = make_harvest(
            self.user, self.farm, harvest_date=date(2026, 10, 21)
        )
        next_year = make_harvest(
            self.user, self.farm, harvest_date=date(2027, 1, 5)
        )

        self.assertEqual(first.harvest_code, 'HL-2026-001')
        self.assertEqual(second.harvest_code, 'HL-2026-002')
        self.assertEqual(next_year.harvest_code, 'HL-2027-001')

    def test_harvest_date_defaults_to_today(self):
        harvest = Harvest.objects.create(
            farm=self.farm,
            user=self.user,
            location='Field A',
            crop_type='Rice',
            quantity_harvested=10,
            harvested_by='Lead',
        )
        self.assertEqual(harvest.harvest_date, timezone.localdate())

    def test_season_is_generated_from_the_harvest_date(self):
        dry = make_harvest(
            self.user, self.farm, harvest_date=date(2026, 2, 10)
        )
        wet = make_harvest(
            self.user, self.farm, harvest_date=date(2026, 8, 10)
        )
        self.assertEqual(dry.harvest_season, 'Dry Season 2026')
        self.assertEqual(wet.harvest_season, 'Wet Season 2026')


class CropMaturityTests(TestCase):
    def setUp(self):
        self.user = make_user('cropuser')
        self.farm = make_farm(self.user)

    def test_expected_harvest_date_is_assigned_from_maturity(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=100,
        )
        self.assertEqual(crop.expected_harvest_date, date(2026, 4, 11))

    def test_expected_harvest_date_recalculates_on_save(self):
        crop = make_crop(self.user, self.farm)
        crop.planting_date = date(2026, 1, 1)
        crop.days_to_maturity = 60
        crop.save()
        crop.refresh_from_db()
        self.assertEqual(crop.expected_harvest_date, date(2026, 3, 2))

    def test_blank_maturity_uses_crop_estimate(self):
        crop = Crop.objects.create(
            farm=self.farm,
            user=self.user,
            name='Rice',
            planting_date=date(2026, 1, 1),
            days_to_maturity=None,
            area_hectares=2,
        )
        self.assertEqual(crop.days_to_maturity, 110)
        self.assertEqual(crop.expected_harvest_date, date(2026, 4, 21))

    def test_maturity_status_stages(self):
        ready = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=90),
            days_to_maturity=90,
        )
        approaching = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=80),
            days_to_maturity=90,
        )
        upcoming = make_crop(
            self.user,
            self.farm,
            name='Tomato',
            planting_date=timezone.localdate() - timedelta(days=20),
            days_to_maturity=90,
        )

        self.assertEqual(ready.maturity_status, 'ready')
        self.assertTrue(ready.is_ready_for_harvest)
        self.assertEqual(ready.days_to_harvest_label, 'Today')
        self.assertEqual(approaching.maturity_status, 'approaching')
        self.assertEqual(upcoming.maturity_status, 'upcoming')

    def test_harvested_and_failed_crops_are_not_ready(self):
        harvested = make_crop(
            self.user,
            self.farm,
            status=Crop.Status.HARVESTED,
            actual_harvest_date=timezone.localdate(),
        )
        failed = make_crop(
            self.user,
            self.farm,
            name='Corn',
            status=Crop.Status.FAILED,
        )
        self.assertFalse(harvested.is_ready_for_harvest)
        self.assertEqual(harvested.maturity_status, 'harvested')
        self.assertFalse(failed.is_ready_for_harvest)
        self.assertEqual(failed.maturity_status, 'failed')

    def test_upcoming_harvests_include_ready_and_near_crops(self):
        ready = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=120),
        )
        approaching = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=80),
        )
        distant = make_crop(
            self.user,
            self.farm,
            name='Tomato',
            planting_date=timezone.localdate() - timedelta(days=10),
        )

        upcoming_ids = [crop.id for crop in get_upcoming_harvests(self.user)]
        self.assertIn(ready.id, upcoming_ids)
        self.assertIn(approaching.id, upcoming_ids)
        self.assertNotIn(distant.id, upcoming_ids)

    def test_board_counts_ready_and_approaching_crops(self):
        make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=120),
        )
        make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=80),
        )
        board = get_harvest_board(self.user)

        self.assertEqual(board['ready_count'], 1)
        self.assertEqual(board['approaching_count'], 1)
        self.assertEqual(len(board['crops']), 2)


class HarvestNotificationServiceTests(TestCase):
    def setUp(self):
        self.user = make_user('notifyuser')
        self.farm = make_farm(self.user)

    def test_approaching_crop_creates_notification(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=80),
        )
        result = evaluate_crop(crop)

        self.assertEqual(result['status'], 'approaching')
        self.assertTrue(result['notification_created'])
        notification = HarvestNotification.objects.get(crop=crop)
        self.assertEqual(notification.kind, HarvestNotification.Kind.APPROACHING)
        self.assertEqual(notification.user, self.user)
        self.assertEqual(
            notification.expected_harvest_date, crop.expected_harvest_date
        )
        crop.refresh_from_db()
        self.assertEqual(crop.status, Crop.Status.MATURING)

    def test_ready_crop_creates_ready_notification(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        result = evaluate_crop(crop)

        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['notification_created'])
        notification = HarvestNotification.objects.get(crop=crop)
        self.assertEqual(notification.kind, HarvestNotification.Kind.READY)
        crop.refresh_from_db()
        self.assertEqual(crop.status, Crop.Status.READY_FOR_HARVEST)

    def test_evaluation_does_not_duplicate_notifications(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        evaluate_crop(crop)
        result = evaluate_crop(crop)

        self.assertFalse(result['notification_created'])
        self.assertEqual(HarvestNotification.objects.filter(crop=crop).count(), 1)

    def test_added_crop_that_is_already_mature_is_notified(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=200),
        )
        result = evaluate_crop(crop)

        self.assertEqual(result['status'], 'ready')
        self.assertTrue(
            HarvestNotification.objects.filter(
                crop=crop, kind=HarvestNotification.Kind.READY
            ).exists()
        )

    def test_changing_the_assigned_date_retires_stale_notifications(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        evaluate_crop(crop)
        old_notification = HarvestNotification.objects.get(crop=crop)

        crop.planting_date = timezone.localdate()
        crop.days_to_maturity = 90
        crop.save()
        evaluate_crop(crop)

        old_notification.refresh_from_db()
        self.assertTrue(old_notification.is_read)
        self.assertEqual(crop.maturity_status, 'upcoming')

    def test_resolve_and_reopen_notifications(self):
        crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        evaluate_crop(crop)
        notification = HarvestNotification.objects.get(crop=crop)

        resolve_crop_notifications(crop)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

        reopen_crop_notifications(crop)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        self.assertTrue(notification.mark_read())
        self.assertFalse(notification.mark_read())

    def test_sync_summary(self):
        make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=120),
        )
        make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=80),
        )
        summary = sync_harvest_readiness(self.user)

        self.assertEqual(summary['ready'], 1)
        self.assertEqual(summary['approaching'], 1)
        self.assertEqual(summary['notifications_created'], 2)

    def test_management_command_checks_readiness(self):
        make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=120),
        )
        output = StringIO()
        call_command(
            'check_harvest_readiness',
            username=self.user.username,
            stdout=output,
        )

        self.assertIn('1 ready', output.getvalue())
        self.assertEqual(
            HarvestNotification.objects.filter(user=self.user).count(), 1
        )


class HarvestWorkflowTests(TestCase):
    def setUp(self):
        self.user = make_user('harvester')
        self.farm = make_farm(self.user)
        self.crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        self.client.force_login(self.user)

    def harvest_payload(self, **overrides):
        data = {
            'crop_id': self.crop.id,
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'quality_condition': 'fresh',
            'moisture_level': '14.5',
            'damaged_quantity': '10',
            'quality_observations': 'Clean batch.',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
            'supervised_by': 'Farm Manager',
            'notes': 'Good harvest condition',
        }
        data.update(overrides)
        return data

    def test_harvest_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('harvests:harvest_list'))
        self.assertEqual(response.status_code, 302)

    def test_harvest_list_renders_crop_readiness_without_schedules(self):
        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user
        response = harvest_list_page(request)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('Harvest Board', content)
        self.assertIn('Ready for Harvest', content)
        self.assertIn(self.crop.name, content)
        self.assertNotIn('Harvest Notifications', content)
        self.assertNotIn('Mark all read', content)
        self.assertNotIn('Harvest Schedules', content)
        self.assertNotIn('Schedule Harvest', content)
        self.assertNotIn('name="harvest_date"', content)

    def test_harvest_date_is_assigned_by_the_system(self):
        response = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(harvest_date='2001-01-01'),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertRegex(data['harvest_code'], r'^HL-\d{4}-\d{3}$')

        harvest = Harvest.objects.get(pk=data['id'])
        self.assertEqual(harvest.harvest_date, timezone.localdate())
        self.assertEqual(harvest.crop, self.crop)
        self.assertEqual(harvest.farm, self.farm)
        self.assertEqual(harvest.harvest_season, self.crop.harvest_season)
        self.assertTrue(harvest.harvest_season)
        self.assertEqual(harvest.quality_condition, 'fresh')

        self.crop.refresh_from_db()
        self.assertEqual(self.crop.status, Crop.Status.HARVESTED)
        self.assertEqual(self.crop.actual_harvest_date, timezone.localdate())

    def test_duplicate_harvest_for_a_crop_is_rejected(self):
        self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        )
        response = self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('already has a harvest record', response.json()['error'])

    def test_crop_is_required_for_new_harvests(self):
        response = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(crop_id=''),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('select the crop', response.json()['error'].lower())

    def test_failed_crop_cannot_be_harvested(self):
        self.crop.status = Crop.Status.FAILED
        self.crop.save(update_fields=['status'])
        response = self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('damaged/failed', response.json()['error'])

    def test_editing_harvest_preserves_the_assigned_date(self):
        harvest_id = self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        ).json()['id']
        original = Harvest.objects.get(pk=harvest_id)

        response = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(
                id=harvest_id,
                harvest_date='2000-02-02',
                quantity_harvested='2600',
                quality_grade='premium',
                workers_count='9',
            ),
        )
        self.assertEqual(response.status_code, 200)
        original.refresh_from_db()
        self.assertEqual(original.harvest_date, timezone.localdate())
        self.assertEqual(original.quantity_harvested, 2600)
        self.assertEqual(original.quality_grade, 'premium')
        self.assertEqual(original.workers_count, 9)

    def test_editing_a_harvest_cannot_relink_to_a_crop_that_was_already_harvested(self):
        harvest_id = self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        ).json()['id']
        other_crop = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(crop_id=other_crop.id, quantity_harvested='100'),
        )

        response = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(id=harvest_id, crop_id=other_crop.id),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('already has a harvest record', response.json()['error'])

    def test_crop_that_is_not_ready_cannot_be_harvested(self):
        future = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate(),
            days_to_maturity=90,
        )
        response = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(crop_id=future.id, quantity_harvested='500'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('not ready for harvest', response.json()['error'])

        future.refresh_from_db()
        self.assertEqual(future.status, Crop.Status.GROWING)
        self.assertFalse(Harvest.objects.filter(crop=future).exists())

    def test_harvest_search_keeps_the_records_section_in_view(self):
        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user
        content = harvest_list_page(request).content.decode()

        self.assertIn(
            f'action="{reverse("harvests:harvest_list")}#harvest-records"',
            content,
        )
        self.assertIn('id="harvest-records"', content)

    def test_harvest_modal_only_lists_harvestable_crops(self):
        future = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate(),
            days_to_maturity=90,
        )
        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user
        content = harvest_list_page(request).content.decode()

        match = re.search(
            r'<select name="crop_id" id="harvest_crop_id".*?</select>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        crop_options = match.group(0)

        self.assertIn(f'<option value="{self.crop.id}"', crop_options)
        self.assertNotIn(f'<option value="{future.id}"', crop_options)

    def test_deleting_harvest_returns_crop_to_ready_and_reopens_notification(self):
        evaluate_crop(self.crop)
        notification = HarvestNotification.objects.get(crop=self.crop)
        self.assertFalse(notification.is_read)

        harvest_id = self.client.post(
            reverse('harvests:harvest_save_ajax'), self.harvest_payload()
        ).json()['id']
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        response = self.client.post(
            reverse('harvests:harvest_delete_ajax', args=[harvest_id])
        )
        self.assertEqual(response.status_code, 200)

        self.crop.refresh_from_db()
        notification.refresh_from_db()
        self.assertIsNone(self.crop.actual_harvest_date)
        self.assertEqual(self.crop.status, Crop.Status.READY_FOR_HARVEST)
        self.assertFalse(notification.is_read)

    def test_deleting_harvest_of_future_crop_keeps_it_maturing(self):
        future = make_crop(
            self.user,
            self.farm,
            name='Corn',
            planting_date=timezone.localdate() - timedelta(days=100),
            days_to_maturity=90,
        )
        harvest_id = self.client.post(
            reverse('harvests:harvest_save_ajax'),
            self.harvest_payload(crop_id=future.id),
        ).json()['id']

        # Reassign the crop's harvest date into the future after harvesting.
        future.refresh_from_db()
        future.planting_date = timezone.localdate()
        future.days_to_maturity = 90
        future.save()

        self.client.post(reverse('harvests:harvest_delete_ajax', args=[harvest_id]))

        future.refresh_from_db()
        self.assertEqual(future.status, Crop.Status.MATURING)
        self.assertIsNone(future.actual_harvest_date)

    def test_harvests_are_scoped_to_the_owner(self):
        other = make_user('other-harvester')
        other_farm = make_farm(other, 'Other Farm')
        other_harvest = make_harvest(other, other_farm)

        detail_response = self.client.get(
            reverse('harvests:harvest_get_ajax', args=[other_harvest.id])
        )
        delete_response = self.client.post(
            reverse('harvests:harvest_delete_ajax', args=[other_harvest.id])
        )
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

    def test_list_only_shows_the_owners_harvests(self):
        own = make_harvest(self.user, self.farm)
        other = make_user('other-owner')
        other_farm = make_farm(other, 'Hidden Farm')
        hidden = make_harvest(other, other_farm, crop_type='Hidden crop')

        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user
        content = harvest_list_page(request).content.decode()

        self.assertIn(own.harvest_code, content)
        self.assertNotIn(hidden.harvest_code, content)


class HarvestNotificationViewTests(TestCase):
    def setUp(self):
        self.user = make_user('notification-view-user')
        self.farm = make_farm(self.user)
        self.crop = make_crop(
            self.user,
            self.farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        evaluate_crop(self.crop)
        self.notification = HarvestNotification.objects.get(crop=self.crop)
        self.client.force_login(self.user)

    def test_single_notification_can_be_marked_read(self):
        response = self.client.post(
            reverse('harvests:harvest_notification_read'),
            {'id': self.notification.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_all_notifications_can_be_marked_read(self):
        response = self.client.post(
            reverse('harvests:harvest_notification_read'), {}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertFalse(
            HarvestNotification.objects.filter(user=self.user, is_read=False).exists()
        )

    def test_dashboard_form_redirects_back_to_the_page(self):
        response = self.client.post(
            reverse('harvests:harvest_notification_read'),
            {'next': reverse('dashboard')},
            HTTP_ACCEPT='text/html',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_notifications_are_scoped_to_the_owner(self):
        other = make_user('other-notification-user')
        other_farm = make_farm(other, 'Other Farm')
        other_crop = make_crop(
            other,
            other_farm,
            planting_date=timezone.localdate() - timedelta(days=100),
        )
        evaluate_crop(other_crop)
        other_notification = HarvestNotification.objects.get(crop=other_crop)

        response = self.client.post(
            reverse('harvests:harvest_notification_read'),
            {'id': other_notification.id},
        )
        self.assertEqual(response.status_code, 404)
        other_notification.refresh_from_db()
        self.assertFalse(other_notification.is_read)

    def test_refresh_readiness_endpoint_updates_counts(self):
        self.notification.is_read = True
        self.notification.save(update_fields=['is_read'])

        response = self.client.post(
            reverse('harvests:harvest_refresh_readiness'), {}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['ready_count'], 1)
        self.assertEqual(data['unread_count'], 0)

    def test_dashboard_shows_the_notification_center(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Notification Center')
        self.assertContains(response, 'Mark all as read')
        self.assertContains(response, self.crop.name)
        self.assertNotContains(response, 'Harvest Notifications')


class HarvestHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user('historyuser')
        self.farm = make_farm(self.user, 'Sunny Fields')
        self.crop = make_crop(
            self.user,
            self.farm,
            name='Sugarcane',
            planting_date=date(2026, 6, 1),
            days_to_maturity=120,
            status=Crop.Status.GROWING,
        )
        self.harvest = make_harvest(
            self.user,
            self.farm,
            crop=self.crop,
            harvest_date=date(2026, 10, 5),
            crop_type='Sugarcane',
            quantity_harvested=2500,
            workers_count=8,
            quality_grade='grade_a',
            notes='Recorded for history monitoring.',
        )
        self.client.force_login(self.user)

    def history_request(self, params=None):
        request = RequestFactory().get(
            reverse('harvests:harvest_history'),
            params or {},
        )
        request.user = self.user
        return harvest_history_page(request)

    def make_other_user_harvest(self):
        other = make_user('historyother')
        other_farm = make_farm(other, 'Other Farm')
        other_harvest = make_harvest(
            other,
            other_farm,
            harvest_date=date(2026, 10, 6),
            crop_type='Rice',
            quantity_harvested=100,
            workers_count=2,
            harvested_by='Other Lead',
        )
        return other, other_farm, other_harvest

    def test_history_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('harvests:harvest_history'))
        self.assertEqual(response.status_code, 302)

    def test_history_page_renders_records_and_monitoring_summary(self):
        response = self.history_request()
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('Harvest History', content)
        self.assertIn(self.harvest.harvest_code, content)
        self.assertIn('Monthly Harvest Activity', content)
        self.assertIn('Quality Mix', content)
        self.assertIn('History by Farm', content)
        self.assertIn('History by Crop', content)
        self.assertIn('Export CSV', content)
        self.assertNotIn('harvest.schedule', content)

    def test_history_filters_keep_the_records_section_in_view(self):
        response = self.history_request()
        content = response.content.decode()

        self.assertIn(
            f'action="{reverse("harvests:harvest_history")}#history-records"',
            content,
        )
        self.assertIn('id="history-records"', content)

    def test_history_filters_by_date_range(self):
        old = make_harvest(
            self.user,
            self.farm,
            crop=self.crop,
            harvest_date=date(2025, 1, 10),
            quantity_harvested=500,
            workers_count=3,
        )

        response = self.history_request({
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        content = response.content.decode()

        self.assertIn(self.harvest.harvest_code, content)
        self.assertNotIn(old.harvest_code, content)

    def test_history_filters_by_farm_and_crop(self):
        other_farm = make_farm(self.user, 'Second Farm', location='Another Place')
        other_crop = make_crop(
            self.user,
            other_farm,
            name='Rice',
            planting_date=date(2026, 7, 1),
        )
        other_harvest = make_harvest(
            self.user,
            other_farm,
            crop=other_crop,
            harvest_date=date(2026, 10, 7),
            crop_type='Rice',
            quantity_harvested=800,
            workers_count=4,
            quality_grade='premium',
            harvested_by='Second Lead',
        )

        response = self.history_request({
            'farm': other_farm.id,
            'crop': other_crop.id,
        })
        content = response.content.decode()

        self.assertIn(other_harvest.harvest_code, content)
        self.assertNotIn(self.harvest.harvest_code, content)

    def test_history_is_scoped_to_owner(self):
        _, _, other_harvest = self.make_other_user_harvest()
        response = self.history_request()
        content = response.content.decode()

        self.assertIn(self.harvest.harvest_code, content)
        self.assertNotIn(other_harvest.harvest_code, content)

    def test_history_csv_export_includes_headers_and_records(self):
        response = self.client.get(reverse('harvests:harvest_history_export'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment; filename=', response['Content-Disposition'])

        content = response.content.decode('utf-8-sig')
        self.assertIn('Harvest ID,Harvest Date,Farm', content)
        self.assertIn(self.harvest.harvest_code, content)
        self.assertIn('Sugarcane', content)
        self.assertIn('Juan Dela Cruz', content)

    def test_history_csv_export_is_scoped_to_owner(self):
        _, _, other_harvest = self.make_other_user_harvest()
        response = self.client.get(reverse('harvests:harvest_history_export'))
        content = response.content.decode('utf-8-sig')

        self.assertIn(self.harvest.harvest_code, content)
        self.assertNotIn(other_harvest.harvest_code, content)


class HarvestQualityRecordingTests(TestCase):
    """Quality & observation recording from the harvest history page."""

    def setUp(self):
        self.user = make_user('qualityuser')
        self.farm = make_farm(self.user, 'Green Acres', location='Tuguegarao, Cagayan')
        self.harvest = make_harvest(
            self.user,
            self.farm,
            harvest_date=date(2026, 10, 12),
            crop_type='Rice',
            quantity_harvested=1200,
            workers_count=5,
        )
        self.url = reverse('harvests:harvest_quality_save')
        self.client.force_login(self.user)

    def record_quality(self, **overrides):
        data = {
            'id': str(self.harvest.id),
            'quality_grade': 'premium',
            'quality_condition': 'fresh',
            'moisture_level': '14.5',
            'damaged_quantity': '25.5',
            'quality_observations': 'Clean batch, no foul odor.',
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_quality_can_be_documented(self):
        response = self.record_quality()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        self.harvest.refresh_from_db()
        self.assertEqual(self.harvest.quality_grade, 'premium')
        self.assertEqual(self.harvest.quality_condition, 'fresh')
        self.assertEqual(self.harvest.moisture_level, 14.5)
        self.assertEqual(self.harvest.damaged_quantity, 25.5)
        self.assertEqual(self.harvest.quality_observations, 'Clean batch, no foul odor.')
        self.assertIsNotNone(self.harvest.quality_recorded_at)
        self.assertTrue(self.harvest.has_quality_record)

    def test_history_page_shows_recorded_quality(self):
        self.record_quality()
        request = RequestFactory().get(reverse('harvests:harvest_history'))
        request.user = self.user
        content = harvest_history_page(request).content.decode()

        self.assertIn('qualityModal', content)
        self.assertIn('Fresh', content)
        self.assertIn('moisture', content)
        self.assertIn('25.5 kg damaged', content)
        self.assertIn('Clean batch, no foul odor.', content)

    def test_quality_fields_can_be_cleared(self):
        self.record_quality()
        response = self.record_quality(
            quality_condition='',
            moisture_level='',
            damaged_quantity='',
            quality_observations='',
        )
        self.assertEqual(response.status_code, 200)

        self.harvest.refresh_from_db()
        self.assertEqual(self.harvest.quality_condition, '')
        self.assertIsNone(self.harvest.moisture_level)
        self.assertIsNone(self.harvest.damaged_quantity)
        self.assertEqual(self.harvest.quality_observations, '')
        self.assertIsNotNone(self.harvest.quality_recorded_at)

    def test_moisture_level_must_be_within_range(self):
        response = self.record_quality(moisture_level='150')
        self.assertEqual(response.status_code, 400)
        self.assertIn('between 0 and 100', response.json()['error'])

        self.harvest.refresh_from_db()
        self.assertIsNone(self.harvest.moisture_level)

    def test_invalid_condition_is_rejected(self):
        response = self.record_quality(quality_condition='soggy')
        self.assertEqual(response.status_code, 400)
        self.assertIn('valid condition', response.json()['error'])

    def test_invalid_grade_is_rejected(self):
        response = self.record_quality(quality_grade='diamond')
        self.assertEqual(response.status_code, 400)
        self.assertIn('valid quality grade', response.json()['error'])

    def test_quality_save_requires_login(self):
        self.client.logout()
        response = self.record_quality()
        self.assertEqual(response.status_code, 302)

    def test_quality_save_is_scoped_to_owner(self):
        other = make_user('qualityother')
        other_farm = make_farm(other, 'Other Farm')
        other_harvest = make_harvest(other, other_farm, crop_type='Corn')

        request = RequestFactory().post(self.url, {
            'id': str(other_harvest.id),
            'quality_grade': 'premium',
            'quality_condition': 'fresh',
        })
        request.user = self.user
        with self.assertRaises(Http404):
            harvest_quality_save_ajax(request)

        other_harvest.refresh_from_db()
        self.assertFalse(other_harvest.has_quality_record)

    def test_history_csv_export_includes_quality_columns(self):
        self.record_quality()
        content = self.client.get(
            reverse('harvests:harvest_history_export')
        ).content.decode('utf-8-sig')

        self.assertIn('Quality,Condition,Moisture (%),Damaged Quantity,Quality Observations', content)
        self.assertIn('Fresh', content)
        self.assertIn('Clean batch, no foul odor.', content)

    def test_quality_details_property(self):
        self.assertEqual(self.harvest.quality_details, [])
        self.assertFalse(self.harvest.has_quality_record)

        self.harvest.quality_condition = 'fresh'
        self.harvest.moisture_level = 14.5
        self.harvest.damaged_quantity = 25
        self.assertEqual(
            self.harvest.quality_details,
            ['Fresh', '14.5% moisture', '25 kg damaged'],
        )


class HarvestListScriptTests(TestCase):
    """Guard the harvest list page's inline script against dead references."""

    def setUp(self):
        self.user = make_user('farmer-script')

    def test_script_only_references_element_ids_that_exist(self):
        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user

        response = harvest_list_page(request)
        content = response.content.decode()

        referenced = set(re.findall(r"getElementById\('([^']+)'\)", content))
        missing = sorted(ref for ref in referenced if f'id="{ref}"' not in content)

        self.assertEqual(
            missing,
            [],
            f'Script references element ids that are not in the page: {missing}',
        )

        ids = re.findall(r'\sid="([^"]+)"', content)
        duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})

        self.assertEqual(
            duplicates,
            [],
            f'Duplicate element ids in the page: {duplicates}',
        )
