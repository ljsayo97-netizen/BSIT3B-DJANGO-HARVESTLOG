from django.test import TestCase
from django.urls import reverse

from apps.crops.models import Crop


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
