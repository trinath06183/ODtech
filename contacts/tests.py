from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from users.models import User
from inventory.models import Product
from .models import Contact, VendorQuote


class VendorQuoteTests(TestCase):
    def setUp(self):
        # Create an admin user for authentication/auth checks
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@example.com',
            password='adminpassword',
            role='Admin'
        )
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='staffpassword',
            role='Staff'
        )

        # Create contact vendor
        self.vendor = Contact.objects.create(
            name='Test Vendor',
            contact_type='Vendor',
            email='vendor@example.com',
            phone='1234567890'
        )

        # Create product
        self.product = Product.objects.create(
            name='Test Product',
            sku='TEST-SKU-1',
            selling_price=1000.00,
            tax_rate=18.00
        )

    def test_vendor_quote_creation(self):
        # Logged in as Admin
        self.client.login(username='adminuser', password='adminpassword')
        
        quote = VendorQuote.objects.create(
            vendor=self.vendor,
            product=self.product,
            quoted_price=750.00,
            quote_date=timezone.now().date(),
            valid_until=timezone.now().date() + timezone.timedelta(days=30),
            lead_time_days=5,
            notes='Test note'
        )

        self.assertEqual(quote.vendor.name, 'Test Vendor')
        self.assertEqual(quote.product.sku, 'TEST-SKU-1')
        self.assertEqual(float(quote.quoted_price), 750.00)
        self.assertEqual(quote.lead_time_days, 5)

    def test_vendor_quotes_cheapest_highlighting(self):
        # Create multiple quotes for the product
        quote_expensive = VendorQuote.objects.create(
            vendor=self.vendor,
            product=self.product,
            quoted_price=800.00,
            quote_date=timezone.now().date()
        )
        quote_cheap = VendorQuote.objects.create(
            vendor=self.vendor,
            product=self.product,
            quoted_price=650.00,
            quote_date=timezone.now().date()
        )

        # Log in and check if the cheapest is identified correctly in view context
        self.client.login(username='adminuser', password='adminpassword')
        response = self.client.get(reverse('vendor_quotes'), {'product': self.product.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cheapest_quote_id'], quote_cheap.id)
        # Check ordering of quotes in context (should be cheap first)
        quotes = list(response.context['quotes'])
        self.assertEqual(quotes[0].id, quote_cheap.id)
        self.assertEqual(quotes[1].id, quote_expensive.id)

    def test_vendor_quote_rbac_enforcement(self):
        # Guest user should be redirected to login
        response = self.client.get(reverse('vendor_quotes'))
        self.assertEqual(response.status_code, 302)

        # Staff user should see the list
        self.client.login(username='staffuser', password='staffpassword')
        response = self.client.get(reverse('vendor_quotes'))
        self.assertEqual(response.status_code, 200)

        # Staff user cannot access create quote form
        response = self.client.get(reverse('vendor_quote_create'))
        self.assertEqual(response.status_code, 302)  # redirected (forbidden by role_required)

        # Admin user CAN access create form
        self.client.login(username='adminuser', password='adminpassword')
        response = self.client.get(reverse('vendor_quote_create'))
        self.assertEqual(response.status_code, 200)
