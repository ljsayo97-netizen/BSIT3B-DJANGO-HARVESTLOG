import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crops.maturity import DEFAULT_MATURITY_DAYS, suggest_maturity_days
from apps.crops.models import Crop
from apps.crops.views import crop_list_page
from apps.farms.models import Farm
from apps.harvests.models import HarvestNotification


class CropModelTests(TestCase):
    def test_crop_str(self):
        farm = Farm(name='Sunny Fields')
        crop = Crop(name='Rice', variety='IR64', farm=farm)
        self.assertIn('Rice', str(crop))

    def test_status_choices(self):
        labels = dict(Crop.Status.choices)
        self.assertEqual(labels['planting'], 'Planted')
        self.assertEqual(labels['growing'], '🌿 Growing')
        self.assertEqual(labels['maturing'], '🌾 Maturing')
        self.assertEqual(labels['ready_for_harvest'], '🟡 Ready for Harvest')
        self.assertEqual(labels['harvested'], '✅ Harvested')
        self.assertEqual(labels['failed'], '⚠️ Damaged/Failed')

    def test_harvest_date_is_derived_from_days_to_maturity(self):
        farm = Farm(name='Sunny Fields')
        crop = Crop(
            name='Rice',
            farm=farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=110,
            area_hectares=1,
        )
        self.assertEqual(crop.calculate_expected_harvest_date(), date(2026, 4, 21))

    def test_maturity_suggestions(self):
        self.assertEqual(suggest_maturity_days('Rice'), 110)
        self.assertEqual(suggest_maturity_days('Sweet corn'), 100)
        self.assertEqual(suggest_maturity_days('Unknown crop'), DEFAULT_MATURITY_DAYS)


class CropViewTests(TestCase):
    def setUp(self):
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

    def save_crop(self, **overrides):
        data = {
            'farm_id': self.farm.id,
            'name': 'Rice',
            'variety': 'IR64',
            'planting_date': '2026-01-01',
            'days_to_maturity': '110',
            'area_hectares': '2.5',
            'status': Crop.Status.PLANTING,
            'quality': '',
        }
        data.update(overrides)
        return self.client.post(reverse('crops:crop_save_ajax'), data)

    def test_crop_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('crops:crop_list'))
        self.assertEqual(response.status_code, 302)

    def test_crop_list_renders(self):
        response = self.client.get(reverse('crops:crop_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'crops/list.html')

    def test_crop_list_shows_system_assigned_date_and_maturity(self):
        Crop.objects.create(
            name='Rice',
            farm=self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=110,
            status=Crop.Status.GROWING,
            area_hectares=2.5,
            user=self.user,
        )
        response = self.client.get(reverse('crops:crop_list'))
        content = response.content.decode()

        self.assertIn('System Harvest Date', content)
        self.assertIn('Days to Maturity', content)
        self.assertIn('Apr 21, 2026', content)
        self.assertIn('110 days', content)
        self.assertNotIn('name="expected_harvest_date"', content)

    def test_farm_detail_panel_shows_details_crops_and_history(self):
        active = Crop.objects.create(
            name='Rice', farm=self.farm, area_hectares=2.5,
            status=Crop.Status.GROWING, user=self.user,
        )
        past = Crop.objects.create(
            name='Corn', farm=self.farm, area_hectares=1.0,
            status=Crop.Status.HARVESTED, user=self.user,
        )

        # Without a selected farm the panel shows only the picker.
        request = RequestFactory().get(reverse('crops:crop_list'))
        request.user = self.user
        self.assertNotIn('Crop History', crop_list_page(request).content.decode())

        # With a farm selected: details, active crops, and crop history appear.
        request = RequestFactory().get(
            reverse('crops:crop_list'), {'farm_detail': self.farm.pk}
        )
        request.user = self.user
        content = crop_list_page(request).content.decode()

        self.assertIn('Farm Details', content)
        self.assertIn(self.farm.location, content)
        self.assertIn('Crop History', content)
        self.assertIn(active.name, content)
        self.assertIn(past.name, content)

    def test_crop_save_derives_the_harvest_date(self):
        planting = timezone.localdate() - timedelta(days=10)
        expected = planting + timedelta(days=110)
        response = self.save_crop(
            planting_date=planting.isoformat(),
            days_to_maturity='110',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['days_to_maturity'], 110)
        self.assertEqual(data['expected_harvest_date'], expected.isoformat())
        self.assertEqual(data['readiness'], 'upcoming')
        self.assertFalse(data['notification_created'])

        crop = Crop.objects.get(pk=data['id'])
        self.assertEqual(crop.expected_harvest_date, expected)

    def test_posted_expected_harvest_date_is_ignored(self):
        response = self.save_crop(expected_harvest_date='2000-01-01')
        self.assertEqual(response.status_code, 200)
        crop = Crop.objects.get(pk=response.json()['id'])
        self.assertEqual(crop.expected_harvest_date, date(2026, 4, 21))

    def test_blank_maturity_uses_the_crop_estimate(self):
        response = self.save_crop(days_to_maturity='')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['days_to_maturity'], 110)

    def test_invalid_days_to_maturity_is_rejected(self):
        response = self.save_crop(days_to_maturity='0')
        self.assertEqual(response.status_code, 400)
        self.assertIn('at least 1', response.json()['error'])

        response = self.save_crop(days_to_maturity='soon')
        self.assertEqual(response.status_code, 400)

    def test_planting_date_is_required(self):
        response = self.save_crop(planting_date='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Planting date is required', response.json()['error'])

    def test_adding_a_mature_crop_creates_a_ready_notification(self):
        planting = (timezone.localdate() - timedelta(days=200)).isoformat()
        response = self.save_crop(planting_date=planting, days_to_maturity='90')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['readiness'], 'ready')
        self.assertTrue(data['notification_created'])
        notification = HarvestNotification.objects.get(crop_id=data['id'])
        self.assertEqual(notification.kind, HarvestNotification.Kind.READY)
        self.assertEqual(notification.user, self.user)

    def test_adding_an_approaching_crop_creates_a_watch_notification(self):
        planting = (timezone.localdate() - timedelta(days=80)).isoformat()
        response = self.save_crop(planting_date=planting, days_to_maturity='90')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['readiness'], 'approaching')
        self.assertTrue(data['notification_created'])
        self.assertTrue(
            HarvestNotification.objects.filter(
                crop_id=data['id'],
                kind=HarvestNotification.Kind.APPROACHING,
            ).exists()
        )

    def test_updating_a_crop_recalculates_the_assigned_date(self):
        response = self.save_crop()
        crop_id = response.json()['id']

        response = self.save_crop(
            id=crop_id,
            planting_date='2026-02-01',
            days_to_maturity='100',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['expected_harvest_date'], '2026-05-12')

    def test_crop_save_requires_login(self):
        self.client.logout()
        response = self.save_crop()
        self.assertEqual(response.status_code, 302)

    def test_crop_save_is_scoped_to_the_owner(self):
        other = get_user_model().objects.create_user(
            username='other', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Other Farm',
            owner='Other',
            location='Elsewhere',
            size_hectares=1,
            date_registered='2026-01-01',
            user=other,
        )

        response = self.save_crop(farm_id=other_farm.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('does not exist', response.json()['error'])

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
