from django.test import TestCase
from django.urls import reverse

from .models import Info


class AnonymousInfoFeatureTests(TestCase):
    def test_anonymous_user_can_create_and_view_info_records(self):
        response = self.client.post(reverse('info:info_save_ajax'), {
            'name': 'Sample Contact',
            'age': '35',
            'address': 'Farm Road',
            'email': 'sample@example.com',
        })

        self.assertEqual(response.status_code, 200)
        info = Info.objects.get(name='Sample Contact')
        self.assertIsNone(info.user)
        self.assertEqual(
            self.client.get(reverse('info:info_get_ajax', args=[info.pk])).status_code,
            200,
        )
