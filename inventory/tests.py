from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from users.models import User
from inventory.models import Product, StockTransaction
from contacts.models import Contact
from documents.models import Document, DocumentItem

class InventoryRBACAndDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_user',
            password='password123',
            role='Admin'
        )
        self.staff = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.accountant = User.objects.create_user(
            username='acct_user',
            password='password123',
            role='Accountant'
        )
        self.product = Product.objects.create(
            name='Test Widget',
            sku='TW-001',
            tax_rate=Decimal('18.00'),
            selling_price=Decimal('100.00'),
            unit='Nos'
        )
        self.contact = Contact.objects.create(
            name='Test Customer',
            contact_type='Customer'
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('inventory_list'))
        self.assertRedirects(response, '/users/login/?next=/inventory/')

    def test_all_roles_can_view_inventory(self):
        for username in ['admin_user', 'staff_user', 'acct_user']:
            self.client.login(username=username, password='password123')
            response = self.client.get(reverse('inventory_list'))
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'inventory/inventory_list.html')
            self.client.logout()

    def test_admin_can_create_product(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('product_create'), {
            'name': 'New Product',
            'sku': 'NP-999',
            'tax_rate': '18.00',
            'selling_price': '150.00',
            'unit': 'Nos',
        })
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertTrue(Product.objects.filter(sku='NP-999').exists())

    def test_staff_cannot_create_product(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('product_create'), {
            'name': 'New Product',
            'sku': 'NP-999',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(Product.objects.filter(sku='NP-999').exists())

    def test_admin_can_edit_product(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('product_edit', args=[self.product.id]), {
            'name': 'Updated Widget',
            'sku': 'TW-001-UPD',
            'tax_rate': '12.00',
            'selling_price': '120.00',
            'unit': 'Nos',
        })
        self.assertRedirects(response, reverse('inventory_list'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Updated Widget')
        self.assertEqual(self.product.sku, 'TW-001-UPD')

    def test_staff_cannot_edit_product(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('product_edit', args=[self.product.id]), {
            'name': 'Updated Widget',
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_admin_can_delete_unreferenced_product(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('product_delete', args=[self.product.id]))
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

    def test_admin_cannot_delete_referenced_product_via_stock_transaction(self):
        StockTransaction.objects.create(
            product=self.product,
            transaction_type='IN',
            quantity=Decimal('10.00')
        )
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('product_delete', args=[self.product.id]))
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_admin_cannot_delete_referenced_product_via_document_item(self):
        doc = Document.objects.create(
            type='QTN',
            contact=self.contact,
            number='QTN-2025-26/001',
            date='2025-05-25'
        )
        DocumentItem.objects.create(
            document=doc,
            product=self.product,
            quantity=Decimal('1.00'),
            unit_price=Decimal('100.00'),
            tax_rate=Decimal('18.00'),
            total=Decimal('118.00')
        )
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('product_delete', args=[self.product.id]))
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_staff_cannot_delete_product(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('product_delete', args=[self.product.id]))
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_admin_can_adjust_stock_in(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('adjust_stock', args=[self.product.id]), {
            'transaction_type': 'IN',
            'quantity': '10.00',
            'remarks': 'Manual initial stock'
        })
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertEqual(self.product.current_stock, 10.00)

    def test_admin_can_adjust_stock_out(self):
        # Seed with initial stock first
        StockTransaction.objects.create(
            product=self.product,
            transaction_type='IN',
            quantity=Decimal('20.00')
        )
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('adjust_stock', args=[self.product.id]), {
            'transaction_type': 'OUT',
            'quantity': '5.00',
            'remarks': 'Manual stock reduction'
        })
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertEqual(self.product.current_stock, 15.00)

    def test_admin_can_adjust_stock_adjustment_reduce(self):
        # Seed with initial stock first
        StockTransaction.objects.create(
            product=self.product,
            transaction_type='IN',
            quantity=Decimal('20.00')
        )
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('adjust_stock', args=[self.product.id]), {
            'transaction_type': 'ADJUSTMENT',
            'adjustment_direction': 'reduce',
            'quantity': '3.00',
            'remarks': 'Inventory count correction'
        })
        self.assertRedirects(response, reverse('inventory_list'))
        self.assertEqual(self.product.current_stock, 17.00)

    def test_staff_cannot_adjust_stock(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('adjust_stock', args=[self.product.id]))
        self.assertRedirects(response, reverse('dashboard'))
        response_post = self.client.post(reverse('adjust_stock', args=[self.product.id]), {
            'transaction_type': 'IN',
            'quantity': '10.00',
        })
        self.assertRedirects(response_post, reverse('dashboard'))
        self.assertEqual(self.product.current_stock, 0.00)


class InventorySearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.product1 = Product.objects.create(
            name='Steel Rod',
            sku='SR-100',
            brand='TATA',
            category='Construction'
        )
        self.product2 = Product.objects.create(
            name='Copper Cable',
            sku='CC-200',
            brand='Polycab',
            category='Electrical'
        )
        self.client.login(username='staff_user', password='password123')

    def test_search_by_product_name(self):
        response = self.client.get(reverse('inventory_list') + '?q=Steel')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product1, response.context['products'])
        self.assertNotIn(self.product2, response.context['products'])

    def test_search_by_sku(self):
        response = self.client.get(reverse('inventory_list') + '?q=CC-200')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product2, response.context['products'])
        self.assertNotIn(self.product1, response.context['products'])

    def test_search_by_brand(self):
        response = self.client.get(reverse('inventory_list') + '?q=Polycab')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product2, response.context['products'])
        self.assertNotIn(self.product1, response.context['products'])

    def test_search_by_category(self):
        response = self.client.get(reverse('inventory_list') + '?q=Construction')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product1, response.context['products'])
        self.assertNotIn(self.product2, response.context['products'])

    def test_suggestions_contains_product_metadata(self):
        response = self.client.get(reverse('inventory_list'))
        self.assertEqual(response.status_code, 200)
        suggestions = response.context['suggestions']
        self.assertIn('Steel Rod', suggestions)
        self.assertIn('SR-100', suggestions)
        self.assertIn('TATA', suggestions)
        self.assertIn('Construction', suggestions)

