from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from contacts.models import Address, Contact
from inventory.models import Product, StockTransaction
from users.models import User

from .models import Document
from .services import DocumentService, NumberingService, PDFService, TaxService


class DocumentServiceTests(TestCase):
    def setUp(self):
        self.customer = Contact.objects.create(
            name="Acme Industries",
            contact_type="Customer",
            gstin="21AAHFO5846M1ZY",
            pan="AAHFO5846M",
        )
        Address.objects.create(
            contact=self.customer,
            address_type="Billing",
            street="Industrial Area",
            city="Bhubaneswar",
            state="Odisha",
            postal_code="751001",
        )
        self.product = Product.objects.create(
            name="Welding Torch",
            sku="WT-001",
            tax_rate=Decimal("18.00"),
            selling_price=Decimal("1000.00"),
        )

    def test_numbering_uses_financial_year_and_sequence(self):
        first = NumberingService.generate_document_number("QTN")
        DocumentService.create_document(
            "QTN",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "1", "rate": "1000", "tax": "18"}],
        )
        second = NumberingService.generate_document_number("QTN")

        self.assertRegex(first, r"^OD-QTN-\d{4}-\d{2}-1$")
        self.assertRegex(second, r"^OD-QTN-\d{4}-\d{2}-2$")

    def test_create_document_uses_decimal_tax_totals(self):
        document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "2", "rate": "1000.50", "tax": "18"}],
            project_name="RFQ-1",
        )

        self.assertTrue(document.number.endswith("-1"))
        self.assertEqual(document.project_name, "RFQ-1")
        self.assertEqual(document.subtotal, Decimal("2001.00"))
        self.assertEqual(document.tax_total, Decimal("360.18"))
        self.assertEqual(document.grand_total, Decimal("2361.18"))
        self.assertEqual(document.items.count(), 1)

    def test_invoice_approval_creates_stock_out_once(self):
        document = DocumentService.create_document(
            "INV",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "3", "rate": "100", "tax": "18"}],
        )

        DocumentService.approve_document(document.id)
        DocumentService.approve_document(document.id)

        self.assertEqual(StockTransaction.objects.count(), 1)
        transaction = StockTransaction.objects.get()
        self.assertEqual(transaction.quantity, Decimal("-3.00"))
        self.assertEqual(transaction.reference_document_id, document.id)

    def test_tax_service_detects_in_state_customer_as_cgst_sgst(self):
        self.assertFalse(TaxService.is_igst(self.customer))

    def test_pdf_service_renders_existing_quotation_template(self):
        document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "1", "rate": "100", "tax": "18"}],
        )

        html = PDFService.render_html(document)

        self.assertIn(document.number, html)
        self.assertIn("Quotation", html)
        self.assertIn("Welding Torch", html)

    def test_create_document_with_global_fixed_discount(self):
        document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [
                {"product_id": self.product.id, "qty": "1", "rate": "1000.00", "tax": "18"},
                {"product_id": self.product.id, "qty": "1", "rate": "2000.00", "tax": "18"},
            ],
            discount_type="fixed",
            discount_value=Decimal("300.00"),
        )
        
        self.assertEqual(document.discount_type, "fixed")
        self.assertEqual(document.discount_value, Decimal("300.00"))
        
        items = list(document.items.all().order_by('id'))
        self.assertEqual(items[0].discount, Decimal("100.00"))
        self.assertEqual(items[1].discount, Decimal("200.00"))
        
        self.assertEqual(document.subtotal, Decimal("2700.00"))
        self.assertEqual(document.tax_total, Decimal("486.00"))
        self.assertEqual(document.grand_total, Decimal("3186.00"))

    def test_create_document_with_global_percentage_discount(self):
        document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [
                {"product_id": self.product.id, "qty": "1", "rate": "1000.00", "tax": "18"},
                {"product_id": self.product.id, "qty": "1", "rate": "2000.00", "tax": "18"},
            ],
            discount_type="percentage",
            discount_value=Decimal("10.00"),
        )
        
        items = list(document.items.all().order_by('id'))
        self.assertEqual(items[0].discount, Decimal("100.00"))
        self.assertEqual(items[1].discount, Decimal("200.00"))
        
        self.assertEqual(document.subtotal, Decimal("2700.00"))
        self.assertEqual(document.tax_total, Decimal("486.00"))
        self.assertEqual(document.grand_total, Decimal("3186.00"))

    def test_create_document_with_individual_discount(self):
        document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [
                {"product_id": self.product.id, "qty": "1", "rate": "1000.00", "tax": "18", "discount": "50"},
                {"product_id": self.product.id, "qty": "1", "rate": "2000.00", "tax": "18", "discount": "150"},
            ],
            discount_type="individual",
        )
        
        items = list(document.items.all().order_by('id'))
        self.assertEqual(items[0].discount, Decimal("50.00"))
        self.assertEqual(items[1].discount, Decimal("150.00"))
        
        self.assertEqual(document.subtotal, Decimal("2800.00"))
        self.assertEqual(document.tax_total, Decimal("504.00"))
        self.assertEqual(document.grand_total, Decimal("3304.00"))


class DocumentRBACAndViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_user',
            password='password123',
            role='Admin'
        )
        self.accountant = User.objects.create_user(
            username='acct_user',
            password='password123',
            role='Accountant'
        )
        self.staff = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.customer = Contact.objects.create(
            name="Acme Industries",
            contact_type="Customer"
        )
        self.product = Product.objects.create(
            name="Welding Torch",
            sku="WT-001",
            tax_rate=Decimal("18.00"),
            selling_price=Decimal("1000.00"),
        )
        self.document = DocumentService.create_document(
            "QTN",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "1", "rate": "100", "tax": "18"}],
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('document_list'))
        self.assertRedirects(response, '/users/login/?next=/documents/')

    def test_all_roles_can_view_document_list(self):
        for username in ['admin_user', 'acct_user', 'staff_user']:
            self.client.login(username=username, password='password123')
            response = self.client.get(reverse('document_list'))
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'documents/document_list.html')
            self.client.logout()

    def test_admin_and_accountant_can_delete_document(self):
        for username in ['admin_user', 'acct_user']:
            # Create a doc for each test since delete deletes it
            doc = DocumentService.create_document(
                "QTN",
                self.customer.id,
                [{"product_id": self.product.id, "qty": "1", "rate": "100", "tax": "18"}],
            )
            self.client.login(username=username, password='password123')
            response = self.client.post(reverse('delete_document', args=[doc.id]))
            self.assertRedirects(response, reverse('document_list'))
            self.assertFalse(Document.objects.filter(id=doc.id).exists())
            self.client.logout()

    def test_staff_cannot_delete_document(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('delete_document', args=[self.document.id]))
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Document.objects.filter(id=self.document.id).exists())

    def test_admin_and_accountant_can_approve_document(self):
        # Create an invoice document to test stock reduction side-effect
        invoice = DocumentService.create_document(
            "INV",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "5", "rate": "100", "tax": "18"}],
        )
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('change_document_status', args=[invoice.id]), {
            'status': 'Approved'
        })
        self.assertRedirects(response, reverse('document_preview', args=[invoice.id]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'Approved')
        # Check stock transaction was created
        self.assertTrue(StockTransaction.objects.filter(reference_document=invoice).exists())
        self.assertEqual(StockTransaction.objects.get(reference_document=invoice).quantity, Decimal('-5.00'))

    def test_admin_and_accountant_can_cancel_document(self):
        self.client.login(username='acct_user', password='password123')
        response = self.client.post(reverse('change_document_status', args=[self.document.id]), {
            'status': 'Cancelled'
        })
        self.assertRedirects(response, reverse('document_preview', args=[self.document.id]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'Cancelled')

    def test_staff_cannot_change_status(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('change_document_status', args=[self.document.id]), {
            'status': 'Approved'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'Draft')

    def test_invalid_status_rejected(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('change_document_status', args=[self.document.id]), {
            'status': 'SuperApproved'
        })
        self.assertRedirects(response, reverse('document_preview', args=[self.document.id]))
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, 'Draft')

    def test_create_document_missing_contact_validation(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('create_invoice'), {
            'action': 'save_as_new',
            'contact': '',
            'type': 'INV',
            'items_json': '[{"product_id": %d, "qty": 1, "rate": 100, "tax": 18}]' % self.product.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'documents/document_create.html')
        messages = list(response.context['messages'])
        self.assertTrue(any("Please select a valid customer" in str(m) for m in messages))
        self.assertEqual(Document.objects.filter(type='INV').count(), 0)

    def test_create_document_missing_items_validation(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('create_invoice'), {
            'action': 'save_as_new',
            'contact': str(self.customer.id),
            'type': 'INV',
            'items_json': '[]',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'documents/document_create.html')
        messages = list(response.context['messages'])
        self.assertTrue(any("Please add at least one line item" in str(m) for m in messages))
        self.assertEqual(Document.objects.filter(type='INV').count(), 0)

    def test_proforma_invoice_preview_renders_as_proforma(self):
        self.client.login(username='staff_user', password='password123')
        proforma = DocumentService.create_document(
            "PRO",
            self.customer.id,
            [{"product_id": self.product.id, "qty": "1", "rate": "100", "tax": "18"}],
        )
        response = self.client.get(reverse('document_html_preview', args=[proforma.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Proforma Invoice")
        self.assertContains(response, proforma.number)
        self.assertNotContains(response, "Tax Invoice")
        self.assertNotContains(response, "Quotation")



class DocumentSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.customer1 = Contact.objects.create(name="Kalinga Institute", contact_type="Customer")
        self.customer2 = Contact.objects.create(name="Acme Industries", contact_type="Customer")
        self.product1 = Product.objects.create(name="Welding Torch Pro", sku="WT-001", tax_rate=Decimal("18.00"))
        self.product2 = Product.objects.create(name="Safety Helmet", sku="SH-002", tax_rate=Decimal("18.00"))

        # QTN-001 for Kalinga with Welding Torch
        self.doc1 = DocumentService.create_document(
            "QTN", self.customer1.id,
            [{"product_id": self.product1.id, "qty": "1", "rate": "500", "tax": "18"}],
            number="OD-QTN-2627-06-1"
        )
        # INV-002 for Acme with Safety Helmet
        self.doc2 = DocumentService.create_document(
            "INV", self.customer2.id,
            [{"product_id": self.product2.id, "qty": "2", "rate": "150", "tax": "18"}],
            number="OD-INV-2627-06-2"
        )
        self.client.login(username='staff_user', password='password123')

    def test_search_by_doc_number(self):
        response = self.client.get(reverse('document_list') + '?q=OD-QTN-2627-06-1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.doc1, response.context['documents'])
        self.assertNotIn(self.doc2, response.context['documents'])

    def test_search_by_customer_name(self):
        response = self.client.get(reverse('document_list') + '?q=Acme')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.doc2, response.context['documents'])
        self.assertNotIn(self.doc1, response.context['documents'])

    def test_search_by_product_name(self):
        response = self.client.get(reverse('document_list') + '?q=Helmet')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.doc2, response.context['documents'])
        self.assertNotIn(self.doc1, response.context['documents'])


class DocumentSortAndFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.customer = Contact.objects.create(name="Test Customer", contact_type="Customer")

        # Create doc 1
        self.doc1 = Document.objects.create(
            type="QTN", contact=self.customer, number="OD-QTN-2627-06-10",
            grand_total=Decimal("100.00"), status="Draft"
        )
        Document.objects.filter(id=self.doc1.id).update(date="2026-05-20")
        self.doc1.refresh_from_db()

        # Create doc 2
        self.doc2 = Document.objects.create(
            type="QTN", contact=self.customer, number="OD-QTN-2627-06-11",
            grand_total=Decimal("500.00"), status="Draft"
        )
        Document.objects.filter(id=self.doc2.id).update(date="2026-05-25")
        self.doc2.refresh_from_db()

        self.client.login(username='staff_user', password='password123')

    def test_filter_by_particular_date(self):
        response = self.client.get(reverse('document_list') + '?date_filter=2026-05-25')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.doc2, response.context['documents'])
        self.assertNotIn(self.doc1, response.context['documents'])

    def test_sort_by_amount_asc(self):
        response = self.client.get(reverse('document_list') + '?sort_by=grand_total')
        self.assertEqual(response.status_code, 200)
        documents = list(response.context['documents'])
        self.assertEqual(documents[0], self.doc1)
        self.assertEqual(documents[1], self.doc2)

    def test_sort_by_amount_desc(self):
        response = self.client.get(reverse('document_list') + '?sort_by=-grand_total')
        self.assertEqual(response.status_code, 200)
        documents = list(response.context['documents'])
        self.assertEqual(documents[0], self.doc2)
        self.assertEqual(documents[1], self.doc1)


class DocumentHtmlPreviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.customer = Contact.objects.create(name="Test Customer", contact_type="Customer")
        self.doc = Document.objects.create(
            type="QTN", contact=self.customer, number="OD-QTN-2627-06-20",
            grand_total=Decimal("100.00"), status="Draft"
        )
        self.client.login(username='staff_user', password='password123')

    def test_html_preview_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('document_html_preview', args=[self.doc.id]))
        self.assertEqual(response.status_code, 302)  # Redirects to login

    def test_html_preview_renders_successfully(self):
        response = self.client.get(reverse('document_html_preview', args=[self.doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.doc.number)


class AllProductsAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff'
        )
        self.product1 = Product.objects.create(name="Welding Torch Pro", sku="WT-001", tax_rate=Decimal("18.00"))
        self.product2 = Product.objects.create(name="Safety Helmet", sku="SH-002", tax_rate=Decimal("18.00"))
        self.client.login(username='staff_user', password='password123')

    def test_all_products_api_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('all_products_api'))
        self.assertEqual(response.status_code, 302)  # Redirects to login page

    def test_all_products_api_returns_all(self):
        response = self.client.get(reverse('all_products_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        # Ordered by name: Safety Helmet, Welding Torch Pro
        self.assertEqual(data[0]['name'], "Safety Helmet")
        self.assertEqual(data[1]['name'], "Welding Torch Pro")

    def test_all_products_api_filtering(self):
        response = self.client.get(reverse('all_products_api') + '?q=Welding')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], "Welding Torch Pro")






