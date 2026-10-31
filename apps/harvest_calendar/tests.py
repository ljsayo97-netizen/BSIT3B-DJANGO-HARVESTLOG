"""Tests for the harvest calendar aggregation and page."""

import html
import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activities.models import FarmActivity
from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.harvests.models import Harvest


def make_user(username='calendar-farmer'):
    return get_user_model().objects.create_user(
        username=username, password='secret1234'
    )


def make_farm(user, name='Calendar Farm', **overrides):
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


def make_activity(user, farm, **overrides):
    data = {
        'farm': farm,
        'user': user,
        'activity_type': FarmActivity.ActivityType.IRRIGATION,
        'location': 'North Field',
        'scheduled_date': timezone.localdate(),
        'assigned_worker': 'Pedro Santos',
        'priority': FarmActivity.Priority.MEDIUM,
        'status': FarmActivity.Status.PENDING,
    }
    data.update(overrides)
    return FarmActivity.objects.create(**data)


def make_harvest(user, farm, crop, **overrides):
    data = {
        'farm': farm,
        'crop': crop,
        'user': user,
        'harvest_date': timezone.localdate(),
        'location': farm.location,
        'crop_type': crop.name,
        'quantity_harvested': 1000,
        'unit': 'kg',
        'quality_grade': Harvest.QualityGrade.STANDARD,
        'workers_count': 3,
        'harvested_by': 'Pedro Santos',
    }
    data.update(overrides)
    return Harvest.objects.create(**data)


class HarvestCalendarTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other_user = make_user('calendar-other')
        self.farm = make_farm(self.user)
        self.crop = make_crop(self.user, self.farm)
        self.client.force_login(self.user)

    def get_events(self, **params):
        response = self.client.get(
            reverse('harvest_calendar:calendar'),
            params,
        )
        self.assertEqual(response.status_code, 200)
        return response.context['calendar_events']

    def get_rendered_events(self, **params):
        """Return events exactly as the browser receives them."""
        response = self.client.get(
            reverse('harvest_calendar:calendar'),
            params,
        )
        self.assertEqual(response.status_code, 200)
        match = re.search(
            r'<script id="harvest-calendar-events" type="application/json">'
            r'(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return json.loads(html.unescape(match.group(1))), response

    def test_calendar_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('harvest_calendar:calendar'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/?next=', response.url)

    def test_calendar_page_renders_with_calendar_library(self):
        response = self.client.get(reverse('harvest_calendar:calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="harvest-calendar"')
        self.assertContains(response, 'fullcalendar/index.global.min.js')
        self.assertContains(response, 'Automatically generated from your crops')

    def test_new_crop_appears_on_the_calendar_automatically(self):
        response = self.client.post(reverse('crops:crop_save_ajax'), {
            'farm_id': self.farm.id,
            'name': 'Corn',
            'variety': 'Sweet Corn',
            'planting_date': timezone.localdate().isoformat(),
            'days_to_maturity': '75',
            'status': Crop.Status.PLANTING,
            'area_hectares': '1.50',
        })
        self.assertEqual(response.status_code, 200)
        crop = Crop.objects.get(pk=response.json()['id'])

        events = self.get_events()
        crop_events = [
            event for event in events
            if event['extendedProps'].get('crop_id') == crop.pk
            and event['extendedProps']['kind'] == 'harvest_expected'
        ]

        self.assertEqual(len(crop_events), 1)
        self.assertEqual(
            crop_events[0]['start'],
            crop.expected_harvest_date.isoformat(),
        )
        self.assertIn('Corn', crop_events[0]['title'])

    def test_harvest_record_uses_the_actual_harvest_date(self):
        harvest = make_harvest(self.user, self.farm, self.crop)
        self.crop.actual_harvest_date = harvest.harvest_date
        self.crop.status = Crop.Status.HARVESTED
        self.crop.save(update_fields=[
            'actual_harvest_date', 'status', 'expected_harvest_date',
            'harvest_season', 'updated_at',
        ])

        events = self.get_events()
        harvest_events = [
            event for event in events
            if event['extendedProps']['kind'] == 'harvest_recorded'
        ]
        crop_events = [
            event for event in events if event['id'] == f'crop-{self.crop.pk}'
        ]

        self.assertEqual(len(harvest_events), 1)
        self.assertEqual(harvest_events[0]['start'], harvest.harvest_date.isoformat())
        self.assertEqual(harvest_events[0]['extendedProps']['harvest_code'], harvest.harvest_code)
        self.assertEqual(crop_events, [])

    def test_activity_appears_on_its_scheduled_date(self):
        activity = make_activity(
            self.user,
            self.farm,
            scheduled_date=timezone.localdate() + timedelta(days=3),
        )

        events = self.get_events()
        activity_events = [
            event for event in events
            if event['extendedProps']['kind'] == 'activity'
        ]

        self.assertEqual(len(activity_events), 1)
        self.assertEqual(
            activity_events[0]['start'],
            activity.scheduled_date.isoformat(),
        )
        self.assertEqual(
            activity_events[0]['extendedProps']['status_key'],
            'pending',
        )

    def test_completed_activity_keeps_its_completion_details(self):
        activity = make_activity(self.user, self.farm)
        activity.apply_status(FarmActivity.Status.IN_PROGRESS)
        activity.apply_status(FarmActivity.Status.COMPLETED)
        activity.save()

        events = self.get_events()
        activity_event = next(
            event for event in events
            if event['extendedProps']['kind'] == 'activity'
        )

        self.assertEqual(activity_event['extendedProps']['status_key'], 'completed')
        self.assertTrue(activity_event['extendedProps']['completed_label'])

    def test_calendar_filters_by_farm(self):
        other_farm = make_farm(self.other_user, name='Other Farm')
        other_crop = make_crop(self.other_user, other_farm, name='Other Rice')
        other_activity = make_activity(self.other_user, other_farm)

        events = self.get_events(farm=self.farm.id)

        self.assertTrue(events)
        for event in events:
            props = event['extendedProps']
            self.assertEqual(props.get('farm_name'), self.farm.name)
        self.assertNotIn(
            other_crop.pk,
            [event['extendedProps'].get('crop_id') for event in events],
        )
        self.assertNotIn(
            other_activity.pk,
            [event['extendedProps'].get('activity_id') for event in events],
        )

    def test_calendar_can_show_activities_only(self):
        make_activity(self.user, self.farm)

        events = self.get_events(show='activities')

        self.assertTrue(events)
        self.assertTrue(
            all(event['extendedProps']['kind'] == 'activity' for event in events)
        )

    def test_calendar_can_show_harvests_only(self):
        make_activity(self.user, self.farm)
        make_harvest(self.user, self.farm, self.crop)

        events = self.get_events(show='harvests')

        self.assertTrue(events)
        self.assertTrue(
            all('harvest' in event['extendedProps']['kind'] for event in events)
        )

    def test_activities_only_renders_activities_and_hides_harvest_content(self):
        make_activity(self.user, self.farm)
        make_harvest(self.user, self.farm, self.crop)

        events, response = self.get_rendered_events(show='activities')

        self.assertTrue(events)
        self.assertTrue(
            all(event['extendedProps']['kind'] == 'activity' for event in events)
        )
        self.assertContains(response, 'value="activities" selected')
        self.assertContains(response, 'Activities only')
        self.assertContains(response, 'Next activities')
        self.assertNotContains(response, 'Upcoming harvests')
        self.assertNotContains(response, 'Harvest recorded')
        self.assertNotContains(response, 'Expected harvest')

    def test_harvests_only_renders_harvests_and_hides_activity_content(self):
        make_activity(self.user, self.farm)
        make_harvest(self.user, self.farm, self.crop)

        events, response = self.get_rendered_events(show='harvests')

        self.assertTrue(events)
        self.assertTrue(
            all('harvest' in event['extendedProps']['kind'] for event in events)
        )
        self.assertContains(response, 'value="harvests" selected')
        self.assertContains(response, 'Harvests only')
        self.assertContains(response, 'Upcoming harvests')
        self.assertNotContains(response, 'Next activities')
        self.assertNotContains(response, 'Activity pending')

    def test_other_users_records_are_not_exposed(self):
        other_farm = make_farm(self.other_user, name='Private Farm')
        other_crop = make_crop(self.other_user, other_farm, name='Private Rice')
        make_activity(self.other_user, other_farm, location='Private Field')

        events = self.get_events()

        event_text = str(events)
        self.assertNotIn(other_farm.name, event_text)
        self.assertNotIn(other_crop.name, event_text)
        self.assertNotIn('Private Field', event_text)

    def test_summary_counts_open_and_completed_activities(self):
        make_activity(self.user, self.farm)
        completed = make_activity(self.user, self.farm, location='South Field')
        completed.apply_status(FarmActivity.Status.IN_PROGRESS)
        completed.apply_status(FarmActivity.Status.COMPLETED)
        completed.save()

        response = self.client.get(reverse('harvest_calendar:calendar'))
        summary = response.context['calendar_summary']

        self.assertEqual(summary['active_activities'], 1)
        self.assertEqual(summary['completed_activities'], 1)

    def test_invalid_filters_are_ignored(self):
        response = self.client.get(
            reverse('harvest_calendar:calendar'),
            {'farm': 'not-a-number', 'crop': '999999', 'show': 'unknown'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['farm_id'])
        self.assertIsNone(response.context['crop_id'])
        self.assertEqual(response.context['source'], 'all')
