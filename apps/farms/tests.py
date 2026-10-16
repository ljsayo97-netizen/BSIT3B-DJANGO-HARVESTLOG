from django.test import TestCase
from django.urls import reverse

from apps.farms.models import Farm


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

    def test_farm_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('farms:farm_list'))
        self.assertEqual(response.status_code, 302)

    def test_farm_list_renders(self):
        response = self.client.get(reverse('farms:farm_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'farms/list.html')
