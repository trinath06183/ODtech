from django.test import TestCase
from django.urls import reverse
from users.models import User
from config.models import CompanyProfile

class ConfigRBACAndSettingsTests(TestCase):
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
        self.company = CompanyProfile.objects.create(
            name='Original Name',
            invoice_prefix='INV-',
            quotation_prefix='QTN-',
            po_prefix='PO-',
            challan_prefix='CHL-'
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('settings'))
        self.assertRedirects(response, '/users/login/?next=/settings/')

    def test_staff_cannot_access_settings(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('settings'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_accountant_cannot_access_settings(self):
        self.client.login(username='acct_user', password='password123')
        response = self.client.get(reverse('settings'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_admin_can_access_settings(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'config/settings.html')

    def test_admin_can_save_settings(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('settings'), {
            'name': 'Updated Company LLC',
            'gstin': '21AAHFO5846M1ZY',
            'pan': 'AAHFO5846M',
            'invoice_prefix': 'INVOICE-',
            'quotation_prefix': 'QUOTATION-',
            'po_prefix': 'PURCHASE-',
            'challan_prefix': 'CHALLAN-',
            'terms_conditions': 'Term 1\nTerm 2'
        })
        self.assertRedirects(response, reverse('settings'))
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Updated Company LLC')
        self.assertEqual(self.company.invoice_prefix, 'INVOICE-')
        self.assertEqual(self.company.gstin, '21AAHFO5846M1ZY')
        self.assertEqual(self.company.pan, 'AAHFO5846M')
        self.assertEqual(self.company.quotation_prefix, 'QUOTATION-')
        self.assertEqual(self.company.po_prefix, 'PURCHASE-')
        self.assertEqual(self.company.challan_prefix, 'CHALLAN-')
        self.assertEqual(self.company.terms_conditions, 'Term 1\nTerm 2')
