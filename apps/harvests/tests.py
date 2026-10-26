from datetime import date, timedelta

import re

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest, HarvestSchedule
from apps.harvests.services import get_upcoming_harvests
from apps.harvests.views import (
    harvest_history_page,
    harvest_list_page,
    harvest_quality_save_ajax,
    harvest_schedule_delete_ajax,
    harvest_schedule_get_ajax,
)


class HarvestModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='modeluser', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Sunny Fields',
            owner='Juan Dela Cruz',
            location='Cauayan, Isabela',
            size_hectares=5.00,
            date_registered=timezone.now(),
            status='active',
            user=self.user,
        )

    def make_harvest(self, harvest_date, **overrides):
        data = {
            'farm': self.farm,
            'user': self.user,
            'harvest_date': harvest_date,
            'location': 'Field A',
            'crop_type': 'Rice',
            'quantity_harvested': 1000,
            'unit': 'kg',
            'quality_grade': 'standard',
            'harvested_by': 'Juan',
        }
        data.update(overrides)
        return Harvest.objects.create(**data)

    def test_harvest_str(self):
        harvest = self.make_harvest(date(2026, 10, 20))
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
        first = self.make_harvest(date(2026, 10, 20))
        second = self.make_harvest(date(2026, 10, 21))
        next_year = self.make_harvest(date(2027, 1, 5))

        self.assertEqual(first.harvest_code, 'HL-2026-001')
        self.assertEqual(second.harvest_code, 'HL-2026-002')
        self.assertEqual(next_year.harvest_code, 'HL-2027-001')


class CropMaturityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cropuser', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Green Valley Farm',
            owner='Manager',
            location='Isabela',
            size_hectares=10.00,
            date_registered=timezone.now(),
            status='active',
            user=self.user,
        )

    def make_crop(self, **overrides):
        today = timezone.localdate()
        data = {
            'farm': self.farm,
            'user': self.user,
            'name': 'Sugarcane',
            'planting_date': today - timedelta(days=90),
            'expected_harvest_date': today + timedelta(days=10),
            'status': Crop.Status.GROWING,
            'area_hectares': 2,
        }
        data.update(overrides)
        return Crop.objects.create(**data)

    def test_approaching_crop_is_listed(self):
        crop = self.make_crop()
        upcoming = get_upcoming_harvests(self.user)
        self.assertEqual([item.id for item in upcoming], [crop.id])
        self.assertEqual(crop.maturity_status, 'approaching')
        self.assertEqual(crop.maturity_label, 'Approaching harvest')

    def test_ready_status_is_listed_even_with_distant_date(self):
        crop = self.make_crop(
            status=Crop.Status.READY_FOR_HARVEST,
            expected_harvest_date=timezone.localdate() + timedelta(days=60),
        )
        upcoming = get_upcoming_harvests(self.user)
        self.assertIn(crop, upcoming)
        self.assertEqual(crop.maturity_status, 'ready')

    def test_harvested_and_failed_crops_are_excluded(self):
        self.make_crop(status=Crop.Status.HARVESTED)
        self.make_crop(status=Crop.Status.FAILED)
        self.assertEqual(get_upcoming_harvests(self.user), [])

    def test_distant_growing_crop_is_not_upcoming(self):
        self.make_crop(expected_harvest_date=timezone.localdate() + timedelta(days=60))
        self.assertEqual(get_upcoming_harvests(self.user), [])


class HarvestWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='harvester', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Green Valley Farm',
            owner='Juan Dela Cruz',
            location='Cauayan, Isabela',
            size_hectares=5.00,
            date_registered=timezone.now(),
            status='active',
            user=self.user,
        )
        self.crop = Crop.objects.create(
            farm=self.farm,
            user=self.user,
            name='Sugarcane',
            planting_date=timezone.localdate() - timedelta(days=100),
            expected_harvest_date=timezone.localdate() + timedelta(days=5),
            status=Crop.Status.GROWING,
            area_hectares=2,
        )
        self.client.force_login(self.user)

    def create_schedule(self, **overrides):
        data = {
            'farm_id': self.farm.id,
            'crop_id': self.crop.id,
            'field_name': 'Field A',
            'scheduled_date': timezone.localdate().isoformat(),
            'expected_quantity': '2500',
            'unit': 'kg',
            'workers_count': '8',
            'assigned_to': 'Harvest Team A',
            'supervisor': 'Farm Manager',
            'status': 'scheduled',
            'notes': 'Bring harvesting equipment.',
        }
        data.update(overrides)
        return self.client.post(reverse('harvests:harvest_schedule_save_ajax'), data)

    def test_harvest_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('harvests:harvest_list'))
        self.assertEqual(response.status_code, 302)

    def test_harvest_list_renders_upcoming_and_scheduling(self):
        request = RequestFactory().get(reverse('harvests:harvest_list'))
        request.user = self.user
        response = harvest_list_page(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Upcoming Harvests', response.content)
        self.assertIn(b'Harvest Schedules', response.content)
        self.assertIn(b'Sugarcane', response.content)

    def test_schedule_can_be_created(self):
        response = self.create_schedule()
        self.assertEqual(response.status_code, 200)
        schedule = HarvestSchedule.objects.get(user=self.user)
        self.assertEqual(schedule.field_name, 'Field A')
        self.assertEqual(schedule.workers_count, 8)
        self.assertEqual(schedule.status, HarvestSchedule.Status.SCHEDULED)

    def test_duplicate_active_schedule_is_rejected(self):
        self.create_schedule()
        response = self.create_schedule()
        self.assertEqual(response.status_code, 400)
        self.assertIn('already has an active harvest schedule', response.json()['error'])

    def test_schedule_requires_workers(self):
        response = self.create_schedule(workers_count='0')
        self.assertEqual(response.status_code, 400)
        self.assertIn('at least one worker', response.json()['error'])

    def test_recording_harvest_completes_schedule_and_crop(self):
        schedule_response = self.create_schedule()
        schedule_id = schedule_response.json()['id']

        response = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'schedule_id': schedule_id,
            'farm_id': self.farm.id,
            'crop_id': self.crop.id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
            'supervised_by': 'Farm Manager',
            'notes': 'Good harvest condition',
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertRegex(data['harvest_code'], r'^HL-\d{4}-\d{3}$')

        schedule = HarvestSchedule.objects.get(pk=schedule_id)
        self.crop.refresh_from_db()
        self.assertEqual(schedule.status, HarvestSchedule.Status.COMPLETED)
        self.assertEqual(schedule.harvest_record.id, data['id'])
        self.assertEqual(self.crop.status, Crop.Status.HARVESTED)
        self.assertEqual(self.crop.actual_harvest_date, timezone.localdate())

    def test_deleting_harvest_reopens_schedule_and_crop(self):
        schedule_response = self.create_schedule()
        schedule_id = schedule_response.json()['id']
        harvest_response = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'schedule_id': schedule_id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
        })
        harvest_id = harvest_response.json()['id']

        response = self.client.post(
            reverse('harvests:harvest_delete_ajax', args=[harvest_id])
        )
        self.assertEqual(response.status_code, 200)

        schedule = HarvestSchedule.objects.get(pk=schedule_id)
        self.crop.refresh_from_db()
        self.assertEqual(schedule.status, HarvestSchedule.Status.SCHEDULED)
        self.assertEqual(self.crop.status, Crop.Status.READY_FOR_HARVEST)
        self.assertIsNone(self.crop.actual_harvest_date)

    def test_editing_scheduled_harvest_keeps_schedule_link(self):
        schedule_id = self.create_schedule().json()['id']
        harvest_id = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'schedule_id': schedule_id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
        }).json()['id']

        response = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'id': harvest_id,
            'schedule_id': schedule_id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2600',
            'unit': 'kg',
            'quality_grade': 'premium',
            'workers_count': '9',
            'harvested_by': 'Team Lead',
            'notes': 'Updated after re-weighing.',
        })
        self.assertEqual(response.status_code, 200)

        harvest = Harvest.objects.get(pk=harvest_id)
        self.assertEqual(harvest.schedule_id, schedule_id)
        self.assertEqual(harvest.quantity_harvested, 2600)
        self.assertEqual(harvest.workers_count, 9)

    def test_editing_harvest_to_unlink_schedule_reopens_it(self):
        schedule_id = self.create_schedule().json()['id']
        harvest_id = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'schedule_id': schedule_id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
        }).json()['id']

        response = self.client.post(reverse('harvests:harvest_save_ajax'), {
            'id': harvest_id,
            'farm_id': self.farm.id,
            'crop_id': self.crop.id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Harvest.objects.get(pk=harvest_id).schedule_id)
        self.assertEqual(
            HarvestSchedule.objects.get(pk=schedule_id).status,
            HarvestSchedule.Status.SCHEDULED,
        )

    def test_recorded_schedule_cannot_be_reopened(self):
        schedule_id = self.create_schedule().json()['id']
        self.client.post(reverse('harvests:harvest_save_ajax'), {
            'schedule_id': schedule_id,
            'harvest_date': timezone.localdate().isoformat(),
            'location': 'Field A',
            'crop_type': 'Sugarcane',
            'quantity_harvested': '2500',
            'unit': 'kg',
            'quality_grade': 'grade_a',
            'workers_count': '8',
            'harvested_by': 'Team Lead',
        })

        response = self.client.post(reverse('harvests:harvest_schedule_save_ajax'), {
            'id': schedule_id,
            'farm_id': self.farm.id,
            'crop_id': self.crop.id,
            'field_name': 'Field A',
            'scheduled_date': timezone.localdate().isoformat(),
            'workers_count': '8',
            'status': 'scheduled',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Delete that harvest record', response.json()['error'])

    def test_schedule_is_scoped_to_owner(self):
        other = get_user_model().objects.create_user(
            username='other', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Other Farm',
            owner='Other',
            location='Elsewhere',
            size_hectares=1,
            date_registered=timezone.now(),
            user=other,
        )
        other_schedule = HarvestSchedule.objects.create(
            farm=other_farm,
            field_name='Field Z',
            scheduled_date=timezone.localdate(),
            workers_count=2,
            user=other,
        )

        request = RequestFactory().get(
            reverse('harvests:harvest_schedule_get_ajax', args=[other_schedule.id])
        )
        request.user = self.user
        with self.assertRaises(Http404):
            harvest_schedule_get_ajax(request, other_schedule.id)

        request = RequestFactory().post(
            reverse('harvests:harvest_schedule_delete_ajax', args=[other_schedule.id])
        )
        request.user = self.user
        with self.assertRaises(Http404):
            harvest_schedule_delete_ajax(request, other_schedule.id)


class HarvestHistoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='historyuser', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Sunny Fields',
            owner='Juan Dela Cruz',
            location='Cauayan, Isabela',
            size_hectares=5.00,
            date_registered=timezone.now(),
            status='active',
            user=self.user,
        )
        self.crop = Crop.objects.create(
            farm=self.farm,
            user=self.user,
            name='Sugarcane',
            planting_date=timezone.localdate() - timedelta(days=100),
            expected_harvest_date=timezone.localdate() + timedelta(days=5),
            status=Crop.Status.GROWING,
            area_hectares=2,
        )
        self.harvest = Harvest.objects.create(
            farm=self.farm,
            crop=self.crop,
            user=self.user,
            harvest_date=date(2026, 10, 5),
            location='Field A',
            crop_type='Sugarcane',
            quantity_harvested=2500,
            unit='kg',
            quality_grade='grade_a',
            workers_count=8,
            harvested_by='Team Lead',
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
        other = get_user_model().objects.create_user(
            username='historyother', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Other Farm',
            owner='Other',
            location='Elsewhere',
            size_hectares=1,
            date_registered=timezone.now(),
            user=other,
        )
        other_harvest = Harvest.objects.create(
            farm=other_farm,
            user=other,
            harvest_date=date(2026, 10, 6),
            location='Field Z',
            crop_type='Rice',
            quantity_harvested=100,
            unit='kg',
            quality_grade='standard',
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

    def test_history_filters_by_date_range(self):
        old = Harvest.objects.create(
            farm=self.farm,
            crop=self.crop,
            user=self.user,
            harvest_date=date(2025, 1, 10),
            location='Field A',
            crop_type='Sugarcane',
            quantity_harvested=500,
            unit='kg',
            quality_grade='standard',
            workers_count=3,
            harvested_by='Team Lead',
        )

        response = self.history_request({
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        content = response.content.decode()

        self.assertIn(self.harvest.harvest_code, content)
        self.assertNotIn(old.harvest_code, content)

    def test_history_filters_by_farm_and_crop(self):
        other_farm = Farm.objects.create(
            name='Second Farm',
            owner='Second Owner',
            location='Another Place',
            size_hectares=3,
            date_registered=timezone.now(),
            user=self.user,
        )
        other_crop = Crop.objects.create(
            farm=other_farm,
            user=self.user,
            name='Rice',
            planting_date=timezone.localdate() - timedelta(days=80),
            expected_harvest_date=timezone.localdate(),
            status=Crop.Status.READY_FOR_HARVEST,
            area_hectares=1,
        )
        other_harvest = Harvest.objects.create(
            farm=other_farm,
            crop=other_crop,
            user=self.user,
            harvest_date=date(2026, 10, 7),
            location='Field B',
            crop_type='Rice',
            quantity_harvested=800,
            unit='kg',
            quality_grade='premium',
            workers_count=4,
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
        self.assertIn('Team Lead', content)

    def test_history_csv_export_is_scoped_to_owner(self):
        _, _, other_harvest = self.make_other_user_harvest()
        response = self.client.get(reverse('harvests:harvest_history_export'))
        content = response.content.decode('utf-8-sig')

        self.assertIn(self.harvest.harvest_code, content)
        self.assertNotIn(other_harvest.harvest_code, content)


class HarvestQualityRecordingTests(TestCase):
    """Quality & observation recording from the harvest history page."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='qualityuser', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Green Acres',
            owner='Maria Santos',
            location='Tuguegarao, Cagayan',
            size_hectares=3.00,
            date_registered=timezone.now(),
            status='active',
            user=self.user,
        )
        self.harvest = Harvest.objects.create(
            farm=self.farm,
            user=self.user,
            harvest_date=date(2026, 10, 12),
            location='Field B',
            crop_type='Rice',
            quantity_harvested=1200,
            unit='kg',
            quality_grade='standard',
            workers_count=5,
            harvested_by='Team Lead',
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
        other = get_user_model().objects.create_user(
            username='qualityother', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Other Farm',
            owner='Other',
            location='Elsewhere',
            size_hectares=1,
            date_registered=timezone.now(),
            status='active',
            user=other,
        )
        other_harvest = Harvest.objects.create(
            farm=other_farm,
            user=other,
            harvest_date=date(2026, 10, 13),
            location='Field Z',
            crop_type='Corn',
            quantity_harvested=50,
            unit='kg',
            quality_grade='standard',
            workers_count=2,
            harvested_by='Other Lead',
        )

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
    """Guard the harvest list page's inline script against dead references.

    A getElementById() call on a missing element returns null, and the
    resulting TypeError aborts the whole script, silently unregistering the
    form submit handlers so harvests and schedules can no longer be saved.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='farmer', password='secret1234'
        )

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
