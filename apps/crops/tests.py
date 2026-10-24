import re

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.crops.models import Crop
from apps.crops.views import crop_list_page


class CropModelTests(TestCase):
    def test_crop_str(self):
        from apps.farms.models import Farm
        farm = Farm(name='Sunny Fields')
        crop = Crop(name='Rice', variety='IR64', farm=farm)
        self.assertIn('Rice', str(crop))

    def test_status_choices(self):
        labels = dict(Crop.Status.choices)
        self.assertEqual(labels['planting'], 'Planting')
        self.assertEqual(labels['growing'], 'Growing')
        self.assertEqual(labels['ready_for_harvest'], 'Ready for Harvest')
        self.assertEqual(labels['harvested'], 'Harvested')
        self.assertEqual(labels['failed'], 'Failed')


class CropViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.farms.models import Farm
        self.user = get_user_model().objects.create_user(
            username='farmer', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Sunny Fields',
            owner='Juan Dela Cruz',
            location='Cauayan, Isabela',
            size_hectares=5.00,
            date_registered='2026-01-01',
            status='active',
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_crop_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('crops:crop_list'))
        self.assertEqual(response.status_code, 302)

    def test_crop_list_renders(self):
        response = self.client.get(reverse('crops:crop_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'crops/list.html')

    def test_script_only_references_element_ids_that_exist(self):
        # A getElementById() call on a missing element returns null, and the
        # resulting TypeError aborts the whole inline script, silently
        # unregistering the submit handler so crops can no longer be saved.
        request = RequestFactory().get(reverse('crops:crop_list'))
        request.user = self.user

        response = crop_list_page(request)
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
