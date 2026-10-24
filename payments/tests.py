import datetime
from django.test import TestCase
from django.urls import reverse
from users.models import User
from payments.models import Expense, user_can_view_fixed_costs
from payments.forms import ExpenseForm


class FixedCostPermissionTests(TestCase):
    def setUp(self):
        self.md_user = User.objects.create_user(
            username='md_user',
            password='password123',
            role='Managing Director',
            email='md@example.com'
        )
        self.admin_user = User.objects.create_user(
            username='admin_user',
            password='password123',
            role='Admin',
            email='admin@example.com'
        )
        self.accounts_user = User.objects.create_user(
            username='accounts_user',
            password='password123',
            role='Accounts',
            email='accounts@example.com'
        )
        self.accountant_user = User.objects.create_user(
            username='accountant_user',
            password='password123',
            role='Accountant',
            email='accountant@example.com'
        )
        self.director_user = User.objects.create_user(
            username='director_user',
            password='password123',
            role='Director',
            email='director@example.com'
        )
        self.hr_user = User.objects.create_user(
            username='hr_user',
            password='password123',
            role='HR',
            email='hr@example.com'
        )
        self.staff_user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff',
            email='staff@example.com'
        )
        self.engineering_user = User.objects.create_user(
            username='eng_user',
            password='password123',
            role='Engineering',
            email='eng@example.com'
        )

        # Create one daily expense and one fixed cost expense
        self.daily_expense = Expense.objects.create(
            title='Petrol for site visit',
            expense_type='Petrol and Diesel',
            amount=500.00,
            date=datetime.date.today(),
            submitted_by=self.staff_user,
            status='Approved',
        )
        self.fixed_cost_expense = Expense.objects.create(
            title='Office Internet Bill',
            expense_type='Internet Bill',
            amount=2500.00,
            date=datetime.date.today(),
            submitted_by=self.admin_user,
            status='Approved',
        )
        self.rent_expense = Expense.objects.create(
            title='Headquarters Office Rent',
            expense_type='Office rent',
            amount=45000.00,
            date=datetime.date.today(),
            submitted_by=self.admin_user,
            status='Approved',
        )

    def test_permission_helper_authorized_roles(self):
        self.assertTrue(user_can_view_fixed_costs(self.md_user))
        self.assertTrue(user_can_view_fixed_costs(self.admin_user))
        self.assertTrue(user_can_view_fixed_costs(self.director_user))
        self.assertTrue(user_can_view_fixed_costs(self.accounts_user))
        self.assertTrue(user_can_view_fixed_costs(self.accountant_user))
        self.assertTrue(user_can_view_fixed_costs(self.hr_user))
        self.assertTrue(self.md_user.can_view_fixed_costs)
        self.assertTrue(self.admin_user.can_view_fixed_costs)
        self.assertTrue(self.accounts_user.can_view_fixed_costs)
        self.assertTrue(self.hr_user.can_view_fixed_costs)
        self.assertTrue(self.hr_user.can_view_confidential_expenses)

    def test_permission_helper_unauthorized_roles(self):
        self.assertFalse(user_can_view_fixed_costs(self.staff_user))
        self.assertFalse(user_can_view_fixed_costs(self.engineering_user))
        self.assertFalse(user_can_view_fixed_costs(None))
        self.assertFalse(self.staff_user.can_view_fixed_costs)
        self.assertFalse(self.engineering_user.can_view_fixed_costs)
        self.assertFalse(self.staff_user.can_view_confidential_expenses)

    def test_expense_is_fixed_cost_property(self):
        self.assertFalse(self.daily_expense.is_fixed_cost)
        self.assertTrue(self.fixed_cost_expense.is_fixed_cost)
        self.assertTrue(self.rent_expense.is_fixed_cost)
        self.assertTrue(self.rent_expense.is_confidential)
        self.assertIn('Staff salary', Expense.get_fixed_cost_categories())
        self.assertIn('Office rent', Expense.get_fixed_cost_categories())
        self.assertIn('OFC rent', Expense.get_fixed_cost_categories())
        self.assertIn('Internet Bill', Expense.get_fixed_cost_categories())
        self.assertIn('Electricity bill', Expense.get_fixed_cost_categories())

    def test_confidential_keyword_detection(self):
        self.assertTrue(Expense.is_fixed_cost_category('Office rent'))
        self.assertTrue(Expense.is_fixed_cost_category('office rent'))
        self.assertTrue(Expense.is_fixed_cost_category('staff salary'))
        self.assertTrue(Expense.is_fixed_cost_category('electricity bills'))
        self.assertTrue(Expense.is_fixed_cost_category('electricity bill'))
        self.assertFalse(Expense.is_fixed_cost_category('Petrol and Diesel'))
        self.assertFalse(Expense.is_fixed_cost_category('Travel'))

    def test_expense_form_choices_unauthorized_user(self):
        form = ExpenseForm(user=self.staff_user)
        choice_groups = [c[0] for c in form.fields['expense_type'].choices]
        self.assertIn('Daily Expenses', choice_groups)
        self.assertNotIn('Fixed Cost', choice_groups)

    def test_expense_form_choices_authorized_user(self):
        form = ExpenseForm(user=self.hr_user)
        choice_groups = [c[0] for c in form.fields['expense_type'].choices]
        self.assertIn('Daily Expenses', choice_groups)
        self.assertIn('Fixed Cost', choice_groups)

    def test_expense_form_validation_unauthorized_rejects_fixed_cost(self):
        form = ExpenseForm(
            data={
                'title': 'Secret salary',
                'expense_type': 'Staff salary',
                'amount': '50000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.staff_user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('expense_type', form.errors)

    def test_expense_form_validation_unauthorized_rejects_custom_confidential_category(self):
        form = ExpenseForm(
            data={
                'title': 'Monthly Office Rent',
                'expense_type': '__custom__',
                'custom_category': 'Office Rent',
                'amount': '40000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.staff_user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('expense_type', form.errors)

    def test_expense_form_validation_authorized_allows_fixed_cost(self):
        form = ExpenseForm(
            data={
                'title': 'Office Rent October',
                'expense_type': 'Office rent',
                'amount': '30000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.hr_user
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_company_overview_permission_properties(self):
        self.assertTrue(self.admin_user.can_view_company_overview)
        self.assertTrue(self.md_user.can_view_company_overview)
        self.assertTrue(self.director_user.can_view_company_overview)
        self.assertTrue(self.accounts_user.can_view_company_overview)
        self.assertTrue(self.accountant_user.can_view_company_overview)
        self.assertTrue(self.hr_user.can_view_company_overview)

        self.assertFalse(self.staff_user.can_view_company_overview)
        self.assertFalse(self.engineering_user.can_view_company_overview)

    def test_financial_dashboard_unauthorized_user_redirected(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('financial_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard', response.url)

    def test_financial_dashboard_authorized_user_access(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse('financial_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_expense_list_confidential_filtering(self):
        # Staff user should only see daily expense, not fixed cost / rent expenses
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('expense_list'))
        self.assertEqual(response.status_code, 200)
        expense_ids = [e.id for e in response.context['expenses']]
        self.assertIn(self.daily_expense.id, expense_ids)
        self.assertNotIn(self.fixed_cost_expense.id, expense_ids)
        self.assertNotIn(self.rent_expense.id, expense_ids)

        # HR user should see all expenses including fixed cost and rent
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse('expense_list'))
        self.assertEqual(response.status_code, 200)
        expense_ids = [e.id for e in response.context['expenses']]
        self.assertIn(self.daily_expense.id, expense_ids)
        self.assertIn(self.fixed_cost_expense.id, expense_ids)
        self.assertIn(self.rent_expense.id, expense_ids)

    def test_expense_form_confidential_checkbox_authorized(self):
        form = ExpenseForm(
            data={
                'title': 'Confidential Client Dinner',
                'expense_type': 'Food Expenses',
                'is_confidential': 'on',
                'amount': '8000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.hr_user
        )
        self.assertTrue(form.is_valid(), form.errors)
        exp = form.save(commit=False)
        exp.submitted_by = self.hr_user
        exp.save()
        self.assertTrue(exp.is_confidential)
        self.assertTrue(exp.is_fixed_cost)

    def test_expense_form_confidential_checkbox_unauthorized_rejected(self):
        form = ExpenseForm(
            data={
                'title': 'Confidential Travel',
                'expense_type': 'Travel',
                'is_confidential': 'on',
                'amount': '15000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.staff_user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('is_confidential', form.errors)

    def test_custom_confidential_expense_hidden_from_normal_users(self):
        # Create an expense with a daily category (Travel) but marked as confidential
        confidential_travel = Expense.objects.create(
            title='Confidential Executive Travel',
            expense_type='Travel',
            is_confidential=True,
            amount=20000.00,
            date=datetime.date.today(),
            submitted_by=self.admin_user,
            status='Approved',
        )

        # Staff user should NOT see it
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('expense_list'))
        expense_ids = [e.id for e in response.context['expenses']]
        self.assertNotIn(confidential_travel.id, expense_ids)

        # HR user SHOULD see it
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse('expense_list'))
        expense_ids = [e.id for e in response.context['expenses']]
        self.assertIn(confidential_travel.id, expense_ids)

    def test_admin_can_edit_expense_directly(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('expense_edit', args=[self.daily_expense.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/expense_form.html')

    def test_user_requires_admin_permission_to_edit(self):
        # Staff user created an expense
        user_expense = Expense.objects.create(
            title='Staff Local Travel',
            expense_type='Travel',
            amount=500.00,
            date=datetime.date.today(),
            submitted_by=self.staff_user,
            status='Pending',
        )
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('expense_edit', args=[user_expense.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/expense_edit_permission.html')

    def test_ask_edit_permission_and_admin_approve_flow(self):
        from tracker.models import Notification
        user_expense = Expense.objects.create(
            title='Office Stationary',
            expense_type='Office stationary',
            amount=1200.00,
            date=datetime.date.today(),
            submitted_by=self.staff_user,
            status='Pending',
        )
        self.client.force_login(self.staff_user)

        # 1. User asks permission
        response = self.client.post(
            reverse('expense_ask_edit_permission', args=[user_expense.id]),
            {'reason': 'Forgot to add GST bill'}
        )
        self.assertRedirects(response, reverse('expense_edit', args=[user_expense.id]))
        user_expense.refresh_from_db()
        self.assertEqual(user_expense.edit_permission_status, 'PENDING')
        self.assertEqual(user_expense.edit_request_reason, 'Forgot to add GST bill')

        # Verify admin received notification
        admin_notif = Notification.objects.filter(user=self.admin_user, title__icontains='Edit Permission Request').first()
        self.assertIsNotNone(admin_notif)
        self.assertIn(user_expense.expense_id, admin_notif.title)

        # 2. Admin approves request
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('expense_decide_edit_permission', args=[user_expense.id, 'approve']))
        self.assertRedirects(response, reverse('expense_detail', args=[user_expense.id]))
        user_expense.refresh_from_db()
        self.assertEqual(user_expense.edit_permission_status, 'APPROVED')

        # Verify user received approval notification
        user_notif = Notification.objects.filter(user=self.staff_user, title__icontains='Edit Permission Approved').first()
        self.assertIsNotNone(user_notif)

        # 3. User now gets the edit form
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('expense_edit', args=[user_expense.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/expense_form.html')


class ExpenseBulkCreateTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='bulk_staff',
            password='password123',
            role='Sales Executive',
            email='bulkstaff@example.com',
            empid='EMP777'
        )
        self.admin_user = User.objects.create_user(
            username='bulk_admin',
            password='password123',
            role='Admin',
            email='bulkadmin@example.com',
            empid='ADM001'
        )

    def test_bulk_create_non_admin_blocked(self):
        """Non-admin / non-superuser must be blocked from bulk expense creation."""
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('expense_bulk_create'))
        self.assertRedirects(response, reverse('expense_list'))

        post_data = {
            'global_employee_code': 'EMP777',
            'row_indices': '0',
            'date_0': '2026-10-24',
            'title_0': 'Unauthorized Bulk Attempt',
            'expense_type_0': 'Travel',
            'amount_0': '500.00',
        }
        post_response = self.client.post(reverse('expense_bulk_create'), post_data)
        self.assertRedirects(post_response, reverse('expense_list'))
        self.assertEqual(Expense.objects.filter(title='Unauthorized Bulk Attempt').count(), 0)

    def test_bulk_create_get(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('expense_bulk_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/expense_bulk_form.html')
        self.assertIn('daily_categories', response.context)
        self.assertTrue(response.context['can_view_fc'])

    def test_bulk_create_post_success(self):
        self.client.force_login(self.admin_user)
        post_data = {
            'global_employee_code': 'ADM001',
            'row_indices': '0,1',
            # Row 0
            'date_0': '2026-10-24',
            'title_0': 'Taxi to client office',
            'expense_type_0': 'Travel',
            'amount_0': '650.00',
            'gst_amount_0': '0.00',
            'employee_code_0': 'ADM001',
            'notes_0': 'Client demo meeting',
            # Row 1
            'date_1': '2026-10-24',
            'title_1': 'Lunch with client team',
            'expense_type_1': 'Food Expenses',
            'amount_1': '1250.50',
            'gst_amount_1': '62.50',
            'employee_code_1': 'ADM001',
            'notes_1': '',
        }
        response = self.client.post(reverse('expense_bulk_create'), post_data)
        self.assertRedirects(response, reverse('expense_list'))

        expenses = Expense.objects.filter(submitted_by=self.admin_user).order_by('id')
        self.assertEqual(expenses.count(), 2)

        exp0 = expenses[0]
        self.assertEqual(exp0.title, 'Taxi to client office')
        self.assertEqual(exp0.expense_type, 'Travel')
        self.assertEqual(float(exp0.amount), 650.00)
        self.assertEqual(exp0.employee_code, 'ADM001')
        self.assertEqual(exp0.status, 'Pending')

        exp1 = expenses[1]
        self.assertEqual(exp1.title, 'Lunch with client team')
        self.assertEqual(exp1.expense_type, 'Food Expenses')
        self.assertEqual(float(exp1.amount), 1250.50)
        self.assertEqual(float(exp1.gst_amount), 62.50)

    def test_bulk_create_validation_error(self):
        self.client.force_login(self.admin_user)
        # Row with missing title
        post_data = {
            'global_employee_code': 'ADM001',
            'row_indices': '0',
            'date_0': '2026-10-24',
            'title_0': '',
            'expense_type_0': 'Travel',
            'amount_0': '500.00',
        }
        response = self.client.post(reverse('expense_bulk_create'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/expense_bulk_form.html')
        self.assertEqual(Expense.objects.filter(submitted_by=self.admin_user).count(), 0)



