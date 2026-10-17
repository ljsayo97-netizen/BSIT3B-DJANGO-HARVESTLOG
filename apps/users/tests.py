from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='secret1234', is_superuser=True
        )
        self.farmer = User.objects.create_user(
            username='farmer', password='secret1234'
        )
        self.client.force_login(self.farmer)

    def test_user_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)

    def test_any_user_can_update_user(self):
        target = User.objects.create_user(username='target', password='secret1234')
        self.client.force_login(self.farmer)
        response = self.client.post(
            reverse('users:user_save_ajax'),
            {
                'id': target.pk,
                'username': 'target',
                'first_name': 'Target',
                'last_name': 'Juan',
                'email': 'target@example.com',
                'is_active': 'true',
                'is_staff': 'false',
            },
        )
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.first_name, 'Target')

    def test_any_user_can_delete_user(self):
        target = User.objects.create_user(username='target', password='secret1234')
        self.client.force_login(self.farmer)
        response = self.client.post(
            reverse('users:user_delete_ajax', args=[target.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=target.pk).exists())

    def test_any_user_can_toggle_active(self):
        target = User.objects.create_user(
            username='target', password='secret1234', is_active=True,
        )
        self.client.force_login(self.farmer)
        response = self.client.post(
            reverse('users:user_toggle_active_ajax', args=[target.pk]),
        )
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_cannot_delete_self(self):
        # A user may not delete their own account.
        self.client.force_login(self.farmer)
        response = self.client.post(
            reverse('users:user_delete_ajax', args=[self.farmer.pk]),
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.farmer.pk).exists())
