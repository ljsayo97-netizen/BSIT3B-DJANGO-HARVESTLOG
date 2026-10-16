from django.test import TestCase
from django.urls import reverse

from apps.inventory.models import InventoryItem, InventoryTransaction


class InventoryItemModelTests(TestCase):
    def test_inventory_item_str(self):
        item = InventoryItem(product_name='Rice', quantity=100, unit='kg')
        self.assertIn('Rice', str(item))

    def test_status_choices(self):
        labels = dict(InventoryItem.Status.choices)
        self.assertEqual(labels['in_stock'], 'In Stock')
        self.assertEqual(labels['low_stock'], 'Low Stock')
        self.assertEqual(labels['out_of_stock'], 'Out of Stock')

    def test_is_low_stock(self):
        item = InventoryItem(product_name='Rice', quantity=5, unit='kg', minimum_stock_level=10)
        self.assertTrue(item.is_low_stock)

        item2 = InventoryItem(product_name='Corn', quantity=50, unit='kg', minimum_stock_level=10)
        self.assertFalse(item2.is_low_stock)

    def test_is_out_of_stock(self):
        item = InventoryItem(product_name='Rice', quantity=0, unit='kg')
        self.assertTrue(item.is_out_of_stock)


class InventoryTransactionModelTests(TestCase):
    def test_transaction_type_choices(self):
        labels = dict(InventoryTransaction.TransactionType.choices)
        self.assertEqual(labels['addition'], 'Addition (Stock In)')
        self.assertEqual(labels['deduction'], 'Deduction (Stock Out)')
        self.assertEqual(labels['adjustment'], 'Adjustment')


class InventoryViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.harvests.models import Harvest
        from apps.farms.models import Farm
        self.user = get_user_model().objects.create_user(
            username='storeman', password='secret1234'
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
        self.harvest = Harvest.objects.create(
            farm=self.farm,
            crop_type='Rice',
            quantity_harvested=1000,
            unit='kg',
            quality_grade='standard',
            harvested_by='Juan',
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_inventory_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('inventory:inventory_list'))
        self.assertEqual(response.status_code, 302)

    def test_inventory_list_renders(self):
        response = self.client.get(reverse('inventory:inventory_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/list.html')
