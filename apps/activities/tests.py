from datetime import timedelta

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm

from apps.activities.models import FarmActivity
from apps.activities.services import get_activities, get_attention_activities
from apps.activities.views import _filter_activities, activity_list_page, activity_status_ajax


class FarmActivityModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager', password='secret1234'
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
            name='Rice',
            variety='NSC 22',
            planting_date=timezone.localdate(),
            area_hectares=2.5,
            user=self.user,
        )

    def make_activity(self, **overrides):
        data = {
            'farm': self.farm,
            'activity_type': FarmActivity.ActivityType.IRRIGATION,
            'location': 'North Field',
            'scheduled_date': timezone.localdate(),
            'assigned_worker': 'Pedro Santos',
            'user': self.user,
        }
        data.update(overrides)
        return FarmActivity.objects.create(**data)

    def test_str_includes_type_field_and_date(self):
        activity = self.make_activity()
        text = str(activity)
        self.assertIn('Irrigation', text)
        self.assertIn('North Field', text)

    def test_activity_type_choices(self):
        labels = dict(FarmActivity.ActivityType.choices)
        self.assertEqual(len(labels), 8)
        for key in (
            'crop_inspection',
            'irrigation',
            'fertilization',
            'weeding',
            'pest_inspection',
            'disease_inspection',
            'harvest_preparation',
            'equipment_inspection',
        ):
            self.assertIn(key, labels)

    def test_defaults_to_pending_with_medium_priority(self):
        activity = self.make_activity()
        self.assertEqual(activity.status, FarmActivity.Status.PENDING)
        self.assertEqual(activity.priority, FarmActivity.Priority.MEDIUM)
        self.assertTrue(activity.is_active)

    def test_status_flow_follows_pending_in_progress_completed(self):
        activity = self.make_activity()

        self.assertTrue(activity.can_transition_to(FarmActivity.Status.IN_PROGRESS))
        self.assertFalse(activity.can_transition_to(FarmActivity.Status.COMPLETED))

        activity.apply_status(FarmActivity.Status.IN_PROGRESS)
        self.assertTrue(activity.can_transition_to(FarmActivity.Status.COMPLETED))
        self.assertTrue(activity.can_transition_to(FarmActivity.Status.PENDING))

        activity.status = FarmActivity.Status.PENDING
        self.assertFalse(activity.can_transition_to(FarmActivity.Status.COMPLETED))

        activity.status = FarmActivity.Status.COMPLETED
        self.assertFalse(activity.can_transition_to(FarmActivity.Status.PENDING))
        self.assertTrue(activity.can_transition_to(FarmActivity.Status.IN_PROGRESS))

    def test_apply_status_tracks_progress_timestamps(self):
        activity = self.make_activity()
        self.assertIsNone(activity.started_at)
        self.assertIsNone(activity.completed_at)

        activity.apply_status(FarmActivity.Status.IN_PROGRESS)
        self.assertIsNotNone(activity.started_at)
        self.assertIsNone(activity.completed_at)

        activity.apply_status(FarmActivity.Status.COMPLETED)
        self.assertIsNotNone(activity.completed_at)

        activity.apply_status(FarmActivity.Status.PENDING)
        self.assertIsNone(activity.started_at)
        self.assertIsNone(activity.completed_at)

    def test_next_status_and_labels(self):
        activity = self.make_activity()
        self.assertEqual(activity.next_status, FarmActivity.Status.IN_PROGRESS)
        self.assertEqual(activity.next_status_label, 'Start Activity')

        activity.status = FarmActivity.Status.IN_PROGRESS
        self.assertEqual(activity.next_status, FarmActivity.Status.COMPLETED)
        self.assertEqual(activity.next_status_label, 'Mark Completed')

        activity.status = FarmActivity.Status.COMPLETED
        self.assertEqual(activity.next_status, FarmActivity.Status.IN_PROGRESS)
        self.assertEqual(activity.next_status_label, 'Reopen Activity')

    def test_overdue_and_due_today(self):
        today = timezone.localdate()
        overdue = self.make_activity(scheduled_date=today - timedelta(days=2))
        due_today = self.make_activity(scheduled_date=today)
        done = self.make_activity(
            scheduled_date=today - timedelta(days=2),
            status=FarmActivity.Status.COMPLETED,
        )
        upcoming = self.make_activity(scheduled_date=today + timedelta(days=3))

        self.assertTrue(overdue.is_overdue)
        self.assertTrue(due_today.due_today)
        self.assertFalse(done.is_overdue)
        self.assertFalse(upcoming.is_overdue)
        self.assertEqual(overdue.days_until, -2)

    def test_badges_and_icons(self):
        activity = self.make_activity(
            priority=FarmActivity.Priority.URGENT,
            activity_type=FarmActivity.ActivityType.PEST_INSPECTION,
        )
        self.assertIn('danger', activity.priority_badge)
        self.assertIn('secondary', activity.status_badge)
        self.assertEqual(activity.icon, 'fas fa-bug')

    def test_service_orders_unfinished_first_and_scopes_by_user(self):
        other_user = get_user_model().objects.create_user(
            username='other', password='secret1234'
        )
        FarmActivity.objects.create(
            farm=self.farm,
            activity_type=FarmActivity.ActivityType.WEEDING,
            location='Other Field',
            scheduled_date=timezone.localdate(),
            assigned_worker='Someone',
            status=FarmActivity.Status.COMPLETED,
            user=other_user,
        )
        self.make_activity(status=FarmActivity.Status.IN_PROGRESS)
        self.make_activity(status=FarmActivity.Status.COMPLETED)

        activities = list(get_activities(self.user))
        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[0].status, FarmActivity.Status.IN_PROGRESS)
        self.assertTrue(all(item.user == self.user for item in activities))

    def test_attention_service_returns_due_and_overdue(self):
        today = timezone.localdate()
        self.make_activity(scheduled_date=today - timedelta(days=1))
        self.make_activity(scheduled_date=today)
        self.make_activity(scheduled_date=today + timedelta(days=5))

        attention = list(get_attention_activities(self.user))
        self.assertEqual(len(attention), 2)


class FarmActivityViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager', password='secret1234'
        )
        self.other_user = get_user_model().objects.create_user(
            username='intruder', password='secret1234'
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
        self.other_farm = Farm.objects.create(
            name='Other Farm',
            owner='Maria',
            location='Tuguegarao',
            size_hectares=1.00,
            date_registered=timezone.now(),
            status='active',
            user=self.other_user,
        )
        self.activity = FarmActivity.objects.create(
            farm=self.farm,
            activity_type=FarmActivity.ActivityType.FERTILIZATION,
            location='Block A',
            scheduled_date=timezone.localdate(),
            assigned_worker='Pedro Santos',
            remarks='Apply 14-14-14 at 90 kg/ha.',
            user=self.user,
        )
        self.client.force_login(self.user)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_list_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('activities:activity_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response.url)

    def test_list_page_renders_with_activity(self):
        request = RequestFactory().get(reverse('activities:activity_list'))
        request.user = self.user
        response = activity_list_page(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Farm Activity Scheduling', response.content)
        self.assertIn(b'Fertilization', response.content)
        self.assertIn(b'Block A', response.content)
        self.assertIn(b'Needs Attention', response.content)

    def test_list_page_renders_empty_state(self):
        self.activity.delete()
        request = RequestFactory().get(reverse('activities:activity_list'))
        request.user = self.user
        response = activity_list_page(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No activities scheduled', response.content)

    def test_filters_by_status_type_priority_and_farm(self):
        FarmActivity.objects.create(
            farm=self.farm,
            activity_type=FarmActivity.ActivityType.IRRIGATION,
            location='Block B',
            scheduled_date=timezone.localdate(),
            assigned_worker='Ana',
            status=FarmActivity.Status.IN_PROGRESS,
            priority=FarmActivity.Priority.URGENT,
            user=self.user,
        )

        def filtered(params):
            request = RequestFactory().get(reverse('activities:activity_list'), params)
            request.user = self.user
            queryset, filters = _filter_activities(request)
            return queryset, filters

        queryset, _ = filtered({'status': 'in_progress'})
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().location, 'Block B')

        queryset, _ = filtered({'type': 'fertilization'})
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().location, 'Block A')

        queryset, _ = filtered({'priority': 'urgent'})
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().location, 'Block B')

        queryset, _ = filtered({'q': 'Block A'})
        self.assertEqual(queryset.count(), 1)

        queryset, _ = filtered({'farm': self.farm.pk})
        self.assertEqual(queryset.count(), 2)

    def test_save_ajax_creates_activity(self):
        response = self.post(reverse('activities:activity_save_ajax'), {
            'activity_type': 'irrigation',
            'farm_id': self.farm.pk,
            'location': 'North Field',
            'scheduled_date': timezone.localdate().isoformat(),
            'assigned_worker': 'Ana Cruz',
            'priority': 'high',
            'status': 'pending',
            'remarks': 'Morning watering.',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['activity']['activity_type'], 'irrigation')
        self.assertEqual(payload['activity']['status'], 'pending')
        self.assertTrue(
            FarmActivity.objects.filter(
                user=self.user,
                activity_type='irrigation',
                location='North Field',
            ).exists()
        )

    def test_save_ajax_rejects_missing_location(self):
        response = self.post(reverse('activities:activity_save_ajax'), {
            'activity_type': 'irrigation',
            'farm_id': self.farm.pk,
            'scheduled_date': timezone.localdate().isoformat(),
            'assigned_worker': 'Ana Cruz',
            'priority': 'high',
            'status': 'pending',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Location is required', response.json()['error'])

    def test_save_ajax_rejects_farm_of_another_user(self):
        response = self.post(reverse('activities:activity_save_ajax'), {
            'activity_type': 'irrigation',
            'farm_id': self.other_farm.pk,
            'location': 'Block Z',
            'scheduled_date': timezone.localdate().isoformat(),
            'assigned_worker': 'Ana Cruz',
            'priority': 'high',
            'status': 'pending',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('does not exist', response.json()['error'])

    def test_save_ajax_rejects_skipping_to_completed(self):
        response = self.post(reverse('activities:activity_save_ajax'), {
            'id': self.activity.pk,
            'activity_type': self.activity.activity_type,
            'farm_id': self.farm.pk,
            'location': self.activity.location,
            'scheduled_date': self.activity.scheduled_date.isoformat(),
            'assigned_worker': self.activity.assigned_worker,
            'priority': 'high',
            'status': 'completed',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Pending -> In Progress -> Completed', response.json()['error'])

    def test_save_ajax_updates_activity(self):
        response = self.post(reverse('activities:activity_save_ajax'), {
            'id': self.activity.pk,
            'activity_type': 'weeding',
            'farm_id': self.farm.pk,
            'location': 'Block A',
            'scheduled_date': self.activity.scheduled_date.isoformat(),
            'assigned_worker': 'Ana Cruz',
            'priority': 'urgent',
            'status': 'pending',
            'remarks': 'Weed the rows.',
        })
        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.activity_type, 'weeding')
        self.assertEqual(self.activity.priority, 'urgent')
        self.assertEqual(self.activity.assigned_worker, 'Ana Cruz')

    def test_status_ajax_walks_the_whole_flow(self):
        url = reverse('activities:activity_status_ajax', args=[self.activity.pk])

        response = self.post(url, {'status': 'in_progress'})
        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, 'in_progress')
        self.assertIsNotNone(self.activity.started_at)

        response = self.post(url, {'status': 'completed'})
        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, 'completed')
        self.assertIsNotNone(self.activity.completed_at)

    def test_status_ajax_blocks_pending_to_completed(self):
        url = reverse('activities:activity_status_ajax', args=[self.activity.pk])
        response = self.post(url, {'status': 'completed'})
        self.assertEqual(response.status_code, 400)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, 'pending')

    def test_status_ajax_defaults_to_next_status(self):
        url = reverse('activities:activity_status_ajax', args=[self.activity.pk])
        response = self.post(url)
        self.assertEqual(response.status_code, 200)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, 'in_progress')

    def test_delete_ajax_removes_own_activity(self):
        response = self.post(reverse('activities:activity_delete_ajax', args=[self.activity.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(FarmActivity.objects.filter(pk=self.activity.pk).exists())

    def test_activities_of_another_user_are_not_reachable(self):
        other_activity = FarmActivity.objects.create(
            farm=self.other_farm,
            activity_type=FarmActivity.ActivityType.WEEDING,
            location='Block Z',
            scheduled_date=timezone.localdate(),
            assigned_worker='Intruder',
            user=self.other_user,
        )

        request = RequestFactory().post(
            reverse('activities:activity_status_ajax', args=[other_activity.pk]),
            {'status': 'in_progress'},
        )
        request.user = self.user
        with self.assertRaises(Http404):
            activity_status_ajax(request, other_activity.pk)

        other_activity.refresh_from_db()
        self.assertEqual(other_activity.status, 'pending')

    def test_export_csv_contains_filtered_rows(self):
        response = self.client.get(
            reverse('activities:activity_export'),
            {'type': 'fertilization'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        content = response.content.decode('utf-8-sig')
        self.assertIn('Fertilization', content)
        self.assertIn('Block A', content)
        self.assertNotIn('Irrigation', content)
