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

    def test_permission_helper_authorized_roles(self):
        self.assertTrue(user_can_view_fixed_costs(self.md_user))
        self.assertTrue(user_can_view_fixed_costs(self.admin_user))
        self.assertTrue(user_can_view_fixed_costs(self.director_user))
        self.assertTrue(user_can_view_fixed_costs(self.accounts_user))
        self.assertTrue(user_can_view_fixed_costs(self.accountant_user))
        self.assertTrue(self.md_user.can_view_fixed_costs)
        self.assertTrue(self.admin_user.can_view_fixed_costs)
        self.assertTrue(self.accounts_user.can_view_fixed_costs)

    def test_permission_helper_unauthorized_roles(self):
        self.assertFalse(user_can_view_fixed_costs(self.staff_user))
        self.assertFalse(user_can_view_fixed_costs(self.engineering_user))
        self.assertFalse(user_can_view_fixed_costs(None))
        self.assertFalse(self.staff_user.can_view_fixed_costs)
        self.assertFalse(self.engineering_user.can_view_fixed_costs)

    def test_expense_is_fixed_cost_property(self):
        self.assertFalse(self.daily_expense.is_fixed_cost)
        self.assertTrue(self.fixed_cost_expense.is_fixed_cost)
        self.assertIn('Staff salary', Expense.get_fixed_cost_categories())
        self.assertIn('OFC rent', Expense.get_fixed_cost_categories())
        self.assertIn('Internet Bill', Expense.get_fixed_cost_categories())

    def test_expense_form_choices_unauthorized_user(self):
        form = ExpenseForm(user=self.staff_user)
        choice_groups = [c[0] for c in form.fields['expense_type'].choices]
        self.assertIn('Daily Expenses', choice_groups)
        self.assertNotIn('Fixed Cost', choice_groups)

    def test_expense_form_choices_authorized_user(self):
        form = ExpenseForm(user=self.admin_user)
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

    def test_expense_form_validation_authorized_allows_fixed_cost(self):
        form = ExpenseForm(
            data={
                'title': 'Office Rent October',
                'expense_type': 'OFC rent',
                'amount': '30000',
                'gst_amount': '0',
                'date': str(datetime.date.today()),
            },
            user=self.admin_user
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_company_overview_permission_properties(self):
        self.assertTrue(self.admin_user.can_view_company_overview)
        self.assertTrue(self.md_user.can_view_company_overview)
        self.assertTrue(self.director_user.can_view_company_overview)
        self.assertTrue(self.accounts_user.can_view_company_overview)
        self.assertTrue(self.accountant_user.can_view_company_overview)

        self.assertFalse(self.staff_user.can_view_company_overview)
        self.assertFalse(self.engineering_user.can_view_company_overview)

    def test_financial_dashboard_unauthorized_user_redirected(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('financial_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard', response.url)

    def test_financial_dashboard_authorized_user_access(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('financial_dashboard'))
        self.assertEqual(response.status_code, 200)
