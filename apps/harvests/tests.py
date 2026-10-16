from django.test import TestCase
from django.urls import reverse

from apps.harvests.models import Harvest


class HarvestModelTests(TestCase):
    def test_harvest_str(self):
        from apps.farms.models import Farm
        farm = Farm(name='Sunny Fields')
        harvest = Harvest(
            farm=farm,
            crop_type='Rice',
            quantity_harvested=1000,
            unit='kg',
            quality_grade='standard',
            harvested_by='Juan',
        )
        self.assertIn('Rice', str(harvest))

    def test_quality_choices(self):
        labels = dict(Harvest.QualityGrade.choices)
        self.assertEqual(labels['premium'], 'Premium')
        self.assertEqual(labels['grade_a'], 'Grade A')
        self.assertEqual(labels['grade_b'], 'Grade B')
        self.assertEqual(labels['grade_c'], 'Grade C')
        self.assertEqual(labels['standard'], 'Standard')
        self.assertEqual(labels['fair'], 'Fair')


class HarvestViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.farms.models import Farm
        self.user = get_user_model().objects.create_user(
            username='harvester', password='secret1234'
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

    def test_harvest_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('harvests:harvest_list'))
        self.assertEqual(response.status_code, 302)

    def test_harvest_list_renders(self):
        response = self.client.get(reverse('harvests:harvest_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'harvests/list.html')
