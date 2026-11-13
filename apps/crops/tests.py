import io
import os
import re
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.templatetags.static import static
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.activities.models import FarmActivity
from apps.crops.categories import infer_category
from apps.crops.images import CROP_IMAGE_FALLBACK, CROP_IMAGE_RULES, crop_image_path
from apps.crops.maturity import DEFAULT_MATURITY_DAYS, suggest_maturity_days
from apps.crops.models import Crop
from apps.crops.views import crop_list_page
from apps.farms.models import Farm
from apps.harvests.models import Harvest, HarvestNotification


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


class CropImageTests(TestCase):
    def test_known_crops_map_to_their_photos(self):
        self.assertEqual(crop_image_path('Rice'), 'img/crops/rice.jpg')
        self.assertEqual(crop_image_path('Palay'), 'img/crops/rice.jpg')
        self.assertEqual(crop_image_path('Sweet corn'), 'img/crops/corn.jpg')
        self.assertEqual(crop_image_path('Tubo'), 'img/crops/sugarcane.jpg')
        self.assertEqual(crop_image_path('Mani'), 'img/crops/peanut.jpg')
        self.assertEqual(crop_image_path('Lansones'), 'img/crops/lanzones.jpg')
        self.assertEqual(crop_image_path('Watermelon'), 'img/crops/watermelon.jpg')
        self.assertEqual(crop_image_path('Kamatis'), 'img/crops/tomato.jpg')
        self.assertEqual(crop_image_path('Talong'), 'img/crops/eggplant.jpg')
        self.assertEqual(crop_image_path('Kamoteng kahoy'), 'img/crops/cassava.jpg')
        self.assertEqual(crop_image_path('Kamote'), 'img/crops/sweet_potato.jpg')
        self.assertEqual(crop_image_path('Luyang dilaw'), 'img/crops/turmeric.jpg')
        self.assertEqual(crop_image_path('Luya'), 'img/crops/ginger.jpg')

    def test_unknown_crop_uses_the_placeholder_photo(self):
        self.assertEqual(crop_image_path('Dragon fruit'), 'img/crops/default.svg')
        self.assertEqual(crop_image_path(''), 'img/crops/default.svg')

    def test_every_mapped_photo_exists(self):
        for _keywords, image_path in CROP_IMAGE_RULES:
            self.assertIsNotNone(finders.find(image_path), image_path)
        self.assertIsNotNone(finders.find(CROP_IMAGE_FALLBACK), CROP_IMAGE_FALLBACK)


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

    def test_crop_list_shows_a_crop_photo_instead_of_the_name(self):
        Crop.objects.create(
            name='Rice',
            farm=self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=110,
            area_hectares=2.5,
            user=self.user,
        )
        response = self.client.get(reverse('crops:crop_list'))
        content = response.content.decode()

        self.assertIn(f'src="{static("img/crops/rice.jpg")}"', content)
        self.assertIn('alt="Rice"', content)
        self.assertIn('title="View details for Rice"', content)
        self.assertIn('data-crop-name="Rice"', content)

    def test_crop_inventory_ajax_groups_records_across_farms(self):
        river_farm = Farm.objects.create(
            name='River Farm',
            owner='Mia Santos',
            location='Pototan, Iloilo',
            size_hectares=2.00,
            date_registered='2026-01-01',
            status='active',
            user=self.user,
        )
        Crop.objects.create(
            name='Rice', farm=self.farm, planting_date=date(2026, 1, 1),
            days_to_maturity=110, area_hectares=2.5, user=self.user,
        )
        Crop.objects.create(
            name='RICE', farm=river_farm, planting_date=date(2026, 2, 1),
            days_to_maturity=110, area_hectares=1.0, user=self.user,
        )
        Crop.objects.create(
            name='Corn', farm=self.farm, area_hectares=1.0, user=self.user,
        )

        response = self.client.get(
            reverse('crops:crop_inventory_ajax'), {'name': 'rice'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'rice')
        self.assertEqual(data['image'], static('img/crops/rice.jpg'))
        self.assertEqual(data['farm_count'], 2)
        self.assertEqual(data['crop_count'], 2)
        self.assertEqual(data['total_area'], 3.5)
        self.assertEqual(
            sorted(farm['name'] for farm in data['farms']),
            ['River Farm', 'Sunny Fields'],
        )
        self.assertEqual(
            sorted(record['farm_name'] for record in data['records']),
            ['River Farm', 'Sunny Fields'],
        )
        self.assertTrue(all(
            record['harvest_date'] for record in data['records']
        ))
        self.assertEqual(
            sorted(record['harvest_date'] for record in data['records']),
            ['Apr 21, 2026', 'May 22, 2026'],
        )

    def test_crop_inventory_ajax_validates_the_crop_name(self):
        response = self.client.get(reverse('crops:crop_inventory_ajax'))
        self.assertEqual(response.status_code, 400)

        response = self.client.get(
            reverse('crops:crop_inventory_ajax'), {'name': 'Dragon fruit'}
        )
        self.assertEqual(response.status_code, 404)

    def test_crop_inventory_ajax_only_returns_owned_crops(self):
        other_user = get_user_model().objects.create_user(
            username='other-farmer', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Hidden Farm',
            size_hectares=1.00,
            date_registered='2026-01-01',
            status='active',
            user=other_user,
        )
        Crop.objects.create(
            name='Rice', farm=other_farm, area_hectares=1.0, user=other_user
        )

        response = self.client.get(
            reverse('crops:crop_inventory_ajax'), {'name': 'Rice'}
        )

        self.assertEqual(response.status_code, 404)

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
        # Both farm-detail tables keep the crop name visible beside the photo.
        self.assertIn('<span class="fw-semibold">Rice</span>', content)
        self.assertIn('<span class="fw-semibold">Corn</span>', content)
        self.assertIn('title="View details for Rice"', content)
        self.assertNotIn('View farms growing', content)

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

    def test_crop_list_renders_the_visual_inventory_filters_and_drawer(self):
        Crop.objects.create(
            name='Tomato',
            category=Crop.Category.VEGETABLE,
            farm=self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=70,
            area_hectares=1.0,
            estimated_yield=Decimal('12.50'),
            user=self.user,
        )
        response = self.client.get(reverse('crops:crop_list'))
        content = response.content.decode()

        self.assertContains(response, 'id="cropInventoryGrid"')
        self.assertContains(response, 'id="cropSearchInput"')
        self.assertContains(response, 'id="cropFarmFilter"')
        self.assertContains(response, 'id="cropStatusFilter"')
        self.assertContains(response, 'id="cropCategoryFilters"')
        self.assertContains(response, 'data-category="vegetable"')
        self.assertContains(response, 'data-category="grain"')
        self.assertContains(response, 'data-category="fruit"')
        self.assertContains(response, 'data-category="other"')
        self.assertContains(response, 'id="cropDrawer"')
        self.assertContains(response, 'id="cropOverviewTab"')
        self.assertContains(response, 'id="cropGrowingTab"')
        self.assertContains(response, 'id="cropHarvestTab"')
        self.assertContains(response, 'id="cropActivitiesTab"')
        self.assertContains(response, 'id="cropDrawerEditBtn"')
        self.assertContains(response, 'id="cropDrawerDeleteBtn"')
        self.assertContains(response, 'id="cropModal"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="image"')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'name="estimated_yield"')
        self.assertContains(response, '12.50 t/ha')
        self.assertContains(response, 'View Details')

        # The category filter counts reflect the crops in the inventory.
        counts = dict(re.findall(
            r'data-category-count="([^"]*)">\s*(\d+)\s*<', content
        ))
        self.assertEqual(counts[''], '1')
        self.assertEqual(counts['vegetable'], '1')
        self.assertEqual(counts['grain'], '0')
        self.assertEqual(counts['fruit'], '0')
        self.assertEqual(counts['other'], '0')

    def test_crop_save_persists_category_yield_and_description(self):
        response = self.save_crop(
            name='Cabbage',
            category=Crop.Category.VEGETABLE,
            estimated_yield='12.5',
            description='Leafy greens for the market.',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['category'], Crop.Category.VEGETABLE)
        self.assertEqual(data['category_display'], 'Vegetables')
        self.assertEqual(data['estimated_yield'], 12.5)

        crop = Crop.objects.get(pk=data['id'])
        self.assertEqual(crop.category, Crop.Category.VEGETABLE)
        self.assertEqual(crop.estimated_yield, Decimal('12.50'))
        self.assertEqual(crop.notes, 'Leafy greens for the market.')

    def test_crop_save_infers_the_category_when_it_is_blank(self):
        response = self.save_crop(name='Tomato', category='')

        self.assertEqual(response.status_code, 200)
        crop = Crop.objects.get(pk=response.json()['id'])
        self.assertEqual(crop.category, Crop.Category.VEGETABLE)

    def test_crop_save_rejects_an_unknown_category(self):
        response = self.save_crop(category='legume')

        self.assertEqual(response.status_code, 400)
        self.assertIn('valid crop category', response.json()['error'])

    def test_crop_save_rejects_an_invalid_estimated_yield(self):
        response = self.save_crop(estimated_yield='-1')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Estimated yield', response.json()['error'])

        response = self.save_crop(estimated_yield='many')
        self.assertEqual(response.status_code, 400)

    def test_updating_a_crop_keeps_the_estimated_yield_when_omitted(self):
        response = self.save_crop(estimated_yield='8.25')
        crop_id = response.json()['id']

        update = {
            'id': crop_id,
            'farm_id': self.farm.id,
            'name': 'Rice',
            'category': Crop.Category.GRAIN,
            'variety': 'IR64',
            'planting_date': '2026-02-01',
            'days_to_maturity': '110',
            'area_hectares': '2.5',
            'status': Crop.Status.GROWING,
            'quality': '',
        }
        response = self.client.post(reverse('crops:crop_save_ajax'), update)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['estimated_yield'], 8.25)
        self.assertEqual(
            Crop.objects.get(pk=crop_id).estimated_yield,
            Decimal('8.25'),
        )
        self.assertEqual(
            Crop.objects.get(pk=crop_id).category,
            Crop.Category.GRAIN,
        )

    def test_crop_get_ajax_returns_the_fields_used_by_the_edit_form(self):
        crop = Crop.objects.create(
            name='Lansones',
            category=Crop.Category.FRUIT,
            variety='Longkong',
            farm=self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=110,
            area_hectares=2.0,
            estimated_yield=Decimal('4.50'),
            notes='Near the creek.',
            user=self.user,
        )

        response = self.client.get(reverse('crops:crop_get_ajax', args=[crop.pk]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['category'], Crop.Category.FRUIT)
        self.assertEqual(data['estimated_yield'], 4.5)
        self.assertEqual(data['notes'], 'Near the creek.')
        self.assertEqual(data['image'], static('img/crops/lanzones.jpg'))
        self.assertFalse(data['image_is_upload'])


class CropDetailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='drawer-farmer', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Lansonesan',
            owner='Juan Dela Cruz',
            location='Cauayan, Isabela',
            size_hectares=5.00,
            date_registered='2026-01-01',
            status='active',
            user=self.user,
        )
        self.crop = Crop.objects.create(
            name='Lansones',
            category=Crop.Category.FRUIT,
            variety='Longkong',
            farm=self.farm,
            planting_date=date(2026, 1, 1),
            days_to_maturity=110,
            area_hectares=2.0,
            estimated_yield=Decimal('4.50'),
            notes='Fruit-bearing trees near the creek.',
            status=Crop.Status.GROWING,
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_crop_detail_ajax_returns_drawer_data(self):
        harvest = Harvest.objects.create(
            farm=self.farm,
            crop=self.crop,
            harvest_date=date(2026, 4, 21),
            quantity_harvested=Decimal('20.00'),
            unit='baskets',
            quality_grade=Harvest.QualityGrade.GRADE_A,
            quality_condition=Harvest.Condition.FRESH,
            location='Field A',
            crop_type='Lansones',
            harvested_by='Juan Dela Cruz',
            user=self.user,
        )
        FarmActivity.objects.create(
            farm=self.farm,
            crop=self.crop,
            activity_type=FarmActivity.ActivityType.IRRIGATION,
            location='Field A',
            assigned_worker='Maria Santos',
            scheduled_date=date(2026, 2, 1),
            status=FarmActivity.Status.PENDING,
            user=self.user,
        )

        response = self.client.get(
            reverse('crops:crop_detail_ajax', args=[self.crop.pk])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Lansones')
        self.assertEqual(data['category'], Crop.Category.FRUIT)
        self.assertEqual(data['category_display'], 'Fruits')
        self.assertEqual(data['farm_name'], 'Lansonesan')
        self.assertEqual(data['farm_location'], 'Cauayan, Isabela')
        self.assertEqual(data['estimated_yield'], 4.5)
        self.assertEqual(data['description'], 'Fruit-bearing trees near the creek.')
        self.assertEqual(data['planting_date'], 'Jan 01, 2026')
        self.assertEqual(data['expected_harvest_date'], 'Apr 21, 2026')
        self.assertEqual(data['harvest_progress'], 100)
        self.assertIsNone(data['soil_type'])
        self.assertIsNone(data['irrigation'])

        self.assertEqual(data['harvest_count'], 1)
        record = data['harvest_records'][0]
        self.assertEqual(record['harvest_code'], harvest.harvest_code)
        self.assertEqual(record['harvest_date'], 'Apr 21, 2026')
        self.assertEqual(record['quantity'], 20.0)
        self.assertEqual(record['unit'], 'baskets')
        self.assertEqual(record['harvest_area'], 2.0)
        self.assertEqual(record['yield_per_hectare'], 10.0)
        self.assertEqual(record['quality_grade_display'], 'Grade A')
        self.assertEqual(
            data['total_harvested'],
            [{'quantity': 20.0, 'unit': 'baskets'}],
        )

        self.assertEqual(data['activity_count'], 1)
        activity = data['activities'][0]
        self.assertEqual(activity['activity_type_display'], 'Irrigation')
        self.assertEqual(activity['assigned_worker'], 'Maria Santos')
        self.assertEqual(activity['scheduled_date'], 'Feb 01, 2026')

        labels = [milestone['label'] for milestone in data['milestones']]
        self.assertEqual(labels, ['Planting', 'Expected harvest'])

    def test_crop_detail_ajax_handles_a_crop_without_records(self):
        response = self.client.get(
            reverse('crops:crop_detail_ajax', args=[self.crop.pk])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['harvest_records'], [])
        self.assertEqual(data['total_harvested'], [])
        self.assertEqual(data['activities'], [])

    def test_crop_detail_ajax_is_scoped_to_the_owner(self):
        other = get_user_model().objects.create_user(
            username='other-drawer-farmer', password='secret1234'
        )
        other_farm = Farm.objects.create(
            name='Hidden Farm',
            size_hectares=1.00,
            date_registered='2026-01-01',
            status='active',
            user=other,
        )
        hidden = Crop.objects.create(
            name='Rice', farm=other_farm, area_hectares=1.0, user=other
        )

        response = self.client.get(
            reverse('crops:crop_detail_ajax', args=[hidden.pk])
        )
        self.assertEqual(response.status_code, 404)


class CropPhotoUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()

        self.user = get_user_model().objects.create_user(
            username='photo-farmer', password='secret1234'
        )
        self.farm = Farm.objects.create(
            name='Photo Farm',
            owner='Photo Owner',
            location='Bacolod, Negros Occidental',
            size_hectares=3.00,
            date_registered='2026-01-01',
            status='active',
            user=self.user,
        )
        self.client.force_login(self.user)

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_upload(self, name='crop.png'):
        buffer = io.BytesIO()
        Image.new('RGB', (32, 24), (34, 197, 94)).save(buffer, format='PNG')
        return SimpleUploadedFile(
            name, buffer.getvalue(), content_type='image/png'
        )

    def post_crop(self, **overrides):
        data = {
            'farm_id': self.farm.id,
            'name': 'Cabbage',
            'category': Crop.Category.VEGETABLE,
            'variety': 'Scorpio',
            'planting_date': '2026-01-01',
            'days_to_maturity': '80',
            'area_hectares': '1.25',
            'estimated_yield': '12.5',
            'status': Crop.Status.GROWING,
            'quality': '',
            'description': 'Photo upload test.',
        }
        data.update(overrides)
        return self.client.post(reverse('crops:crop_save_ajax'), data)

    def test_uploaded_photo_is_saved_and_used_for_the_crop(self):
        response = self.post_crop(image=self.make_upload())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['image_is_upload'])
        self.assertIn('/media/crops/', data['image'])

        crop = Crop.objects.get(pk=data['id'])
        self.assertTrue(crop.image.name.startswith('crops/'))
        self.assertTrue(os.path.exists(crop.image.path))
        self.assertEqual(crop.display_image_url, crop.image.url)

    def test_replacing_a_photo_deletes_the_old_file(self):
        response = self.post_crop(image=self.make_upload('first.png'))
        crop = Crop.objects.get(pk=response.json()['id'])
        old_path = crop.image.path
        self.assertTrue(os.path.exists(old_path))

        response = self.post_crop(
            id=crop.pk,
            image=self.make_upload('second.png'),
        )
        self.assertEqual(response.status_code, 200)
        crop.refresh_from_db()
        self.assertEqual(crop.image.name.rsplit('/', 1)[-1], 'second.png')
        self.assertTrue(os.path.exists(crop.image.path))
        self.assertFalse(os.path.exists(old_path))

    def test_removing_a_photo_deletes_the_file_and_restores_the_fallback(self):
        response = self.post_crop(image=self.make_upload())
        crop = Crop.objects.get(pk=response.json()['id'])
        old_path = crop.image.path

        response = self.post_crop(id=crop.pk, remove_image='1')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['image_is_upload'])
        self.assertEqual(data['image'], static('img/crops/cabbage.jpg'))

        crop.refresh_from_db()
        self.assertFalse(crop.image)
        self.assertFalse(os.path.exists(old_path))

    def test_deleting_a_crop_removes_its_uploaded_photo(self):
        response = self.post_crop(image=self.make_upload())
        crop = Crop.objects.get(pk=response.json()['id'])
        image_path = crop.image.path
        self.assertTrue(os.path.exists(image_path))

        response = self.client.post(
            reverse('crops:crop_delete_ajax', args=[crop.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Crop.objects.filter(pk=crop.pk).exists())
        self.assertFalse(os.path.exists(image_path))

    def test_non_image_upload_is_rejected(self):
        response = self.post_crop(
            image=SimpleUploadedFile(
                'notes.txt', b'not really an image', content_type='text/plain'
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('valid image file', response.json()['error'])
        self.assertFalse(Crop.objects.exists())

    def test_corrupt_image_upload_is_rejected(self):
        response = self.post_crop(
            image=SimpleUploadedFile(
                'broken.png', b'not really a png', content_type='image/png'
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('valid image file', response.json()['error'])
        self.assertFalse(Crop.objects.exists())

    def test_oversized_photo_is_rejected(self):
        upload = SimpleUploadedFile(
            'huge.png',
            b'x' * (5 * 1024 * 1024 + 1),
            content_type='image/png',
        )
        response = self.post_crop(image=upload)

        self.assertEqual(response.status_code, 400)
        self.assertIn('5 MB', response.json()['error'])
        self.assertFalse(Crop.objects.exists())


class CropCategoryTests(TestCase):
    def test_category_inference_for_english_names(self):
        self.assertEqual(infer_category('Rice'), Crop.Category.GRAIN)
        self.assertEqual(infer_category('Sweet corn'), Crop.Category.GRAIN)
        self.assertEqual(infer_category('Tomato'), Crop.Category.VEGETABLE)
        self.assertEqual(infer_category('Cabbage'), Crop.Category.VEGETABLE)
        self.assertEqual(infer_category('Lansones'), Crop.Category.FRUIT)
        self.assertEqual(infer_category('Watermelon'), Crop.Category.FRUIT)
        self.assertEqual(infer_category('Dragon fruit'), Crop.Category.OTHER)
        self.assertEqual(infer_category(''), Crop.Category.OTHER)

    def test_category_inference_for_filipino_names(self):
        self.assertEqual(infer_category('Palay'), Crop.Category.GRAIN)
        self.assertEqual(infer_category('Kamatis'), Crop.Category.VEGETABLE)
        self.assertEqual(infer_category('Talong'), Crop.Category.VEGETABLE)
        self.assertEqual(infer_category('Saging'), Crop.Category.FRUIT)
        self.assertEqual(infer_category('Mangga'), Crop.Category.FRUIT)
