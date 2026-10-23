from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.models import Crop
from apps.farms.models import Farm
from apps.farms.views import (
    farm_get_ajax,
    farm_list_page,
    farm_permanent_delete,
    farm_save_ajax,
)


class FarmModelTests(TestCase):
    def test_farm_str_is_name(self):
        farm = Farm(name='Sunny Fields')
        self.assertEqual(str(farm), 'Sunny Fields')

    def test_status_choices(self):
        labels = dict(Farm.Status.choices)
        self.assertEqual(labels['active'], 'Active')
        self.assertEqual(labels['inactive'], 'Inactive')
        self.assertEqual(labels['archived'], 'Archived')


class FarmViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            username='farmer', password='secret1234'
        )
        self.client.force_login(self.user)

    def _create_farm(self, name='Test Farm', **overrides):
        values = {
            'user': self.user,
            'name': name,
            'owner': 'Owner',
            'location': 'Location',
            'size_hectares': 1,
            'date_registered': timezone.now(),
            'status': Farm.Status.ACTIVE,
        }
        values.update(overrides)
        return Farm.objects.create(**values)

    def test_farm_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('farms:farm_list'))
        self.assertEqual(response.status_code, 302)

    def test_farm_list_renders(self):
        request = RequestFactory().get(reverse('farms:farm_list'))
        request.user = self.user

        response = farm_list_page(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Farm Management', response.content.decode())

    def test_soft_delete_hides_farm_and_restore_brings_it_back(self):
        farm = self._create_farm()

        farm.soft_delete()
        farm.refresh_from_db()

        self.assertTrue(farm.is_deleted)
        self.assertIsNotNone(farm.deleted_at)
        self.assertFalse(Farm.objects.filter(pk=farm.pk).exists())
        self.assertTrue(Farm.all_objects.filter(pk=farm.pk, is_deleted=True).exists())

        farm.restore()
        farm.refresh_from_db()

        self.assertFalse(farm.is_deleted)
        self.assertIsNone(farm.deleted_at)
        self.assertTrue(Farm.objects.filter(pk=farm.pk).exists())

    def test_deleted_farm_related_records_still_resolve(self):
        farm = self._create_farm()
        crop = Crop.objects.create(
            user=self.user,
            farm=farm,
            name='Rice',
            area_hectares=1,
        )

        farm.soft_delete()
        crop = Crop.objects.select_related('farm').get(pk=crop.pk)

        self.assertEqual(crop.farm.name, farm.name)

    def test_delete_endpoint_moves_farm_to_deleted_log(self):
        farm = self._create_farm(name='Delete Me')

        response = self.client.post(
            reverse('farms:farm_delete_ajax', args=[farm.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(Farm.objects.filter(pk=farm.pk).exists())
        deleted = Farm.all_objects.get(pk=farm.pk)
        self.assertTrue(deleted.is_deleted)
        self.assertIsNotNone(deleted.deleted_at)

    def test_restore_endpoint_restores_deleted_farm(self):
        farm = self._create_farm(name='Restore Me')
        farm.soft_delete()

        response = self.client.post(
            reverse('farms:farm_restore', args=[farm.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farms:farm_list'))
        farm.refresh_from_db()
        self.assertFalse(farm.is_deleted)
        self.assertIsNone(farm.deleted_at)
        self.assertTrue(Farm.objects.filter(pk=farm.pk).exists())

    def test_restore_requires_post(self):
        farm = self._create_farm()
        farm.soft_delete()

        response = self.client.get(
            reverse('farms:farm_restore', args=[farm.pk])
        )

        self.assertEqual(response.status_code, 405)
        farm.refresh_from_db()
        self.assertTrue(farm.is_deleted)

    def test_permanent_delete_removes_deleted_farm_and_related_records(self):
        farm = self._create_farm(name='Delete Forever')
        crop = Crop.objects.create(
            user=self.user,
            farm=farm,
            name='Rice',
            area_hectares=1,
        )
        farm.soft_delete()

        response = self.client.post(
            reverse('farms:farm_permanent_delete', args=[farm.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farms:farm_list'))
        self.assertFalse(Farm.all_objects.filter(pk=farm.pk).exists())
        self.assertFalse(Crop.objects.filter(pk=crop.pk).exists())

    def test_permanent_delete_requires_a_deleted_farm(self):
        farm = self._create_farm()
        request = RequestFactory().post(
            reverse('farms:farm_permanent_delete', args=[farm.pk])
        )
        request.user = self.user

        with self.assertRaises(Http404):
            farm_permanent_delete(request, farm.pk)

        self.assertTrue(Farm.objects.filter(pk=farm.pk).exists())

    def test_permanent_delete_requires_post(self):
        farm = self._create_farm()
        farm.soft_delete()

        response = self.client.get(
            reverse('farms:farm_permanent_delete', args=[farm.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Farm.all_objects.filter(pk=farm.pk).exists())

    def test_bulk_restore_restores_only_selected_farms(self):
        first = self._create_farm(name='Restore One')
        second = self._create_farm(name='Restore Two')
        untouched = self._create_farm(name='Leave Deleted')
        for farm in (first, second, untouched):
            farm.soft_delete()

        response = self.client.post(
            reverse('farms:farm_bulk_restore'),
            data={'farm_ids': [str(first.pk), str(second.pk)]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farms:farm_list'))
        first.refresh_from_db()
        second.refresh_from_db()
        untouched.refresh_from_db()
        self.assertFalse(first.is_deleted)
        self.assertFalse(second.is_deleted)
        self.assertTrue(untouched.is_deleted)

    def test_bulk_permanent_delete_removes_selected_farms_and_related_records(self):
        first = self._create_farm(name='Delete One')
        second = self._create_farm(name='Delete Two')
        untouched = self._create_farm(name='Keep Deleted')
        crop = Crop.objects.create(
            user=self.user,
            farm=first,
            name='Rice',
            area_hectares=1,
        )
        for farm in (first, second, untouched):
            farm.soft_delete()

        response = self.client.post(
            reverse('farms:farm_bulk_permanent_delete'),
            data={'farm_ids': [str(first.pk), str(second.pk)]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('farms:farm_list'))
        self.assertFalse(
            Farm.all_objects.filter(pk__in=[first.pk, second.pk]).exists()
        )
        self.assertTrue(Farm.all_objects.filter(pk=untouched.pk).exists())
        self.assertFalse(Crop.objects.filter(pk=crop.pk).exists())

    def test_bulk_actions_require_post(self):
        for url_name in (
            'farms:farm_bulk_restore',
            'farms:farm_bulk_permanent_delete',
        ):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 405)

    def test_bulk_actions_without_selection_do_not_change_farms(self):
        farm = self._create_farm(name='Still Deleted')
        farm.soft_delete()

        restore_response = self.client.post(
            reverse('farms:farm_bulk_restore'),
            data={},
        )
        delete_response = self.client.post(
            reverse('farms:farm_bulk_permanent_delete'),
            data={},
        )

        self.assertEqual(restore_response.status_code, 302)
        self.assertEqual(delete_response.status_code, 302)
        farm.refresh_from_db()
        self.assertTrue(farm.is_deleted)

    def test_deleted_farm_cannot_be_fetched_through_active_endpoints(self):
        farm = self._create_farm()
        farm.soft_delete()

        get_request = RequestFactory().get(
            reverse('farms:farm_get_ajax', args=[farm.pk])
        )
        get_request.user = self.user
        save_request = RequestFactory().post(
            reverse('farms:farm_save_ajax'),
            data={
                'id': farm.pk,
                'name': 'Changed',
                'owner': 'Owner',
                'location': 'Location',
                'size_hectares': '1',
                'status': Farm.Status.ACTIVE,
            },
        )
        save_request.user = self.user

        with self.assertRaises(Http404):
            farm_get_ajax(get_request, farm.pk)
        with self.assertRaises(Http404):
            farm_save_ajax(save_request)

    def test_farm_list_ajax_excludes_deleted_farms(self):
        active_farm = self._create_farm(name='Active Farm')
        deleted_farm = self._create_farm(name='Deleted Farm')
        deleted_farm.soft_delete()

        response = self.client.get(reverse('farms:farm_list_ajax'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual([row['id'] for row in data['data']], [active_farm.pk])

    def test_farm_list_context_counts_active_and_deleted_farms(self):
        self._create_farm(name='Active Farm')
        deleted_farm = self._create_farm(name='Deleted Farm')
        deleted_farm.soft_delete()

        request = RequestFactory().get(reverse('farms:farm_list'))
        request.user = self.user
        response = farm_list_page(request)
        content = response.content.decode()

        self.assertIn('Total Registered Farms: 1', content)
        self.assertIn('Deleted Log', content)
        self.assertIn('Active Farm', content)
        self.assertIn('Deleted Farm', content)
        self.assertIn('id="selectAllDeletedFarms"', content)
        self.assertIn('deleted-farm-checkbox', content)
        self.assertIn('name="farm_ids"', content)
        self.assertIn(f'value="{deleted_farm.pk}"', content)
        self.assertIn('id="bulkRestoreBtn"', content)
        self.assertIn('id="bulkDeleteBtn"', content)
        self.assertIn(reverse('farms:farm_bulk_restore'), content)
        self.assertIn(reverse('farms:farm_bulk_permanent_delete'), content)
