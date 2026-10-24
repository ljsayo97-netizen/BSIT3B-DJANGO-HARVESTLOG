import re

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


class FarmListScriptTests(TestCase):
    """Guard the farm list page's markup and inline script.

    The inline script binds the deleted-log bulk controls by element id, so
    the page has to render each of those ids exactly once. A missing element
    makes getElementById() return null, and a duplicated id makes it return
    the wrong element; either way the script crashes or stops driving the
    visible controls, which is how registering a farm silently stopped
    saving.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            username='farmer', password='secret1234'
        )
        Farm.objects.create(
            user=self.user,
            name='Active Farm',
            owner='Owner',
            location='Location',
            size_hectares=1,
            date_registered=timezone.now(),
            status=Farm.Status.ACTIVE,
        )
        deleted_farm = Farm.objects.create(
            user=self.user,
            name='Deleted Farm',
            owner='Owner',
            location='Location',
            size_hectares=1,
            date_registered=timezone.now(),
            status=Farm.Status.ACTIVE,
        )
        deleted_farm.soft_delete()

    def _page_content(self):
        request = RequestFactory().get(reverse('farms:farm_list'))
        request.user = self.user
        return farm_list_page(request).content.decode()

    def test_script_only_references_element_ids_that_exist(self):
        content = self._page_content()

        referenced = set(re.findall(r"getElementById\('([^']+)'\)", content))
        missing = sorted(ref for ref in referenced if f'id="{ref}"' not in content)

        self.assertEqual(
            missing,
            [],
            f'Script references element ids that are not in the page: {missing}',
        )

    def test_every_element_id_is_unique(self):
        # Duplicating an id (for example to keep a hidden copy around) makes
        # getElementById() return the first match, so the visible controls
        # are never updated by the script.
        content = self._page_content()

        ids = re.findall(r'\sid="([^"]+)"', content)
        duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})

        self.assertEqual(
            duplicates,
            [],
            f'Duplicate element ids in the page: {duplicates}',
        )

    def test_bulk_restore_and_delete_controls_use_the_real_form(self):
        # "Restore Selected" and "Delete Selected" submit the form that holds
        # the deleted-farm checkboxes, so those controls must be the only
        # elements carrying their ids.
        content = self._page_content()

        for element_id in (
            'deletedFarmsBulkForm',
            'selectAllDeletedFarms',
            'deletedSelectedCount',
            'bulkRestoreBtn',
            'bulkDeleteBtn',
        ):
            self.assertEqual(
                content.count(f'id="{element_id}"'),
                1,
                f'Expected exactly one #{element_id} in the page.',
            )

        self.assertEqual(content.count('form="deletedFarmsBulkForm"'), 2)


class FarmContactDetailTests(TestCase):
    """Auto-generated farm IDs and the optional owner contact details."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            username='farmer', password='secret1234'
        )
        self.client.force_login(self.user)

    def _create_farm(self, **overrides):
        values = {
            'user': self.user,
            'name': 'Contact Farm',
            'owner': 'Juan Dela Cruz',
            'location': 'Cauayan, Isabela',
            'size_hectares': 1,
            'date_registered': timezone.now(),
            'status': Farm.Status.ACTIVE,
        }
        values.update(overrides)
        return Farm.objects.create(**values)

    def _save_request(self, **data):
        payload = {
            'name': 'New Farm',
            'owner': 'Juan Dela Cruz',
            'location': 'Cauayan, Isabela',
            'size_hectares': '1.5',
            'status': Farm.Status.ACTIVE,
        }
        payload.update(data)
        return self.client.post(reverse('farms:farm_save_ajax'), payload)

    def test_farm_code_is_auto_generated_from_the_farm_id(self):
        farm = self._create_farm(name='First Farm')
        other = self._create_farm(name='Second Farm')

        self.assertEqual(farm.farm_code, f'FARM-{farm.pk:04d}')
        self.assertEqual(other.farm_code, f'FARM-{other.pk:04d}')
        self.assertNotEqual(farm.farm_code, other.farm_code)
        self.assertRegex(farm.farm_code, r'^FARM-\d{4,}$')

    def test_farm_code_is_stable_across_updates(self):
        farm = self._create_farm()
        original_code = farm.farm_code

        farm.name = 'Renamed Farm'
        farm.save()

        farm.refresh_from_db()
        self.assertEqual(farm.farm_code, original_code)

    def test_registered_farm_gets_its_code_from_the_save_endpoint(self):
        response = self._save_request()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        farm = Farm.objects.get(user=self.user)
        self.assertEqual(farm.farm_code, f'FARM-{farm.pk:04d}')
        self.assertEqual(data['farm_code'], farm.farm_code)

    def test_farm_code_posted_by_the_form_is_ignored(self):
        response = self._save_request(farm_code='FARM-9999')

        self.assertEqual(response.status_code, 200)
        farm = Farm.objects.get(user=self.user)
        self.assertNotEqual(farm.farm_code, 'FARM-9999')
        self.assertEqual(farm.farm_code, f'FARM-{farm.pk:04d}')

    def test_save_endpoint_stores_contact_details(self):
        response = self._save_request(
            email='carl@example.com',
            contact_number='0917-123-4567',
            zip_code='3300',
        )

        self.assertEqual(response.status_code, 200)
        farm = Farm.objects.get(user=self.user)
        self.assertEqual(farm.email, 'carl@example.com')
        self.assertEqual(farm.contact_number, '0917-123-4567')
        self.assertEqual(farm.zip_code, '3300')

        data = response.json()
        self.assertEqual(data['email'], 'carl@example.com')
        self.assertEqual(data['contact_number'], '0917-123-4567')
        self.assertEqual(data['zip_code'], '3300')

    def test_save_endpoint_can_clear_contact_details(self):
        farm = self._create_farm(
            email='carl@example.com',
            contact_number='0917-123-4567',
            zip_code='3300',
        )

        response = self._save_request(
            id=str(farm.pk),
            email='',
            contact_number='',
            zip_code='',
        )

        self.assertEqual(response.status_code, 200)
        farm.refresh_from_db()
        self.assertEqual(farm.email, '')
        self.assertEqual(farm.contact_number, '')
        self.assertEqual(farm.zip_code, '')

    def test_save_endpoint_rejects_an_invalid_email(self):
        response = self._save_request(email='not-an-email')

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json()['error'].lower())
        self.assertFalse(Farm.objects.filter(user=self.user).exists())

    def test_contact_details_are_shown_in_grid_view_but_not_in_the_list(self):
        farm = self._create_farm(
            name='Grid Farm',
            email='carl@example.com',
            contact_number='0917-123-4567',
            zip_code='3300',
        )

        request = RequestFactory().get(reverse('farms:farm_list'))
        request.user = self.user
        content = farm_list_page(request).content.decode()

        table_view = content.split('<!-- TABLE VIEW -->', 1)[1].split('<!-- GRID VIEW -->', 1)[0]
        grid_view = content.split('<!-- GRID VIEW -->', 1)[1].split('<!-- Pagination -->', 1)[0]

        for value in (farm.farm_code, farm.email, farm.contact_number, 'ZIP 3300'):
            self.assertIn(value, grid_view)
            self.assertNotIn(value, table_view)

    def test_registration_modal_includes_the_new_fields(self):
        request = RequestFactory().get(reverse('farms:farm_list'))
        request.user = self.user
        content = farm_list_page(request).content.decode()

        self.assertIn('id="farm_code"', content)
        self.assertIn('Auto-generated (e.g. FARM-0001)', content)
        self.assertIn('id="farm_email"', content)
        self.assertIn('placeholder="carl@example.com"', content)
        self.assertIn('id="farm_contact_number"', content)
        self.assertIn('placeholder="09XX-XXX-XXXX"', content)
        self.assertIn('id="farm_zip_code"', content)
