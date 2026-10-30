import json
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from hr.models import LeaveType, LeaveAllocation, AttendanceRecord, LeaveRequest

User = get_user_model()


class HRPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Regular employee
        self.employee = User.objects.create_user(
            username='employee1',
            email='emp1@example.com',
            password='password123',
            role='Sales Executive',
            first_name='John',
            last_name='Doe',
        )

        # Another employee
        self.other_employee = User.objects.create_user(
            username='employee2',
            email='emp2@example.com',
            password='password123',
            role='Engineer',
            first_name='Jane',
            last_name='Smith',
        )

        # HR user
        self.hr_user = User.objects.create_user(
            username='hr_user',
            email='hr@example.com',
            password='password123',
            role='HR',
            first_name='Helen',
            last_name='HR',
        )

        # Admin user
        self.admin_user = User.objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='password123',
            role='Admin',
            first_name='Adam',
            last_name='Admin',
        )

        # Managing Director user
        self.md_user = User.objects.create_user(
            username='md_user',
            email='md@example.com',
            password='password123',
            role='Managing Director',
            first_name='Mike',
            last_name='Director',
        )

        # Leave types
        self.casual_leave, _ = LeaveType.objects.get_or_create(
            code='CL',
            defaults={
                'name': 'Casual Leave',
                'default_days': 12,
                'is_active': True,
            }
        )

    def test_regular_user_cannot_view_hr_dashboard(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('hr:dashboard'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

    def test_hr_admin_md_can_view_hr_dashboard(self):
        for user in [self.hr_user, self.admin_user, self.md_user]:
            self.client.force_login(user)
            response = self.client.get(reverse('hr:dashboard'))
            self.assertEqual(response.status_code, 200)

    def test_regular_user_blocked_from_admin_actions(self):
        self.client.force_login(self.employee)

        # Mark attendance
        response = self.client.get(reverse('hr:mark_attendance'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

        # Leave requests review list
        response = self.client.get(reverse('hr:leave_requests'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

        # Monthly report
        response = self.client.get(reverse('hr:attendance_report'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

        # Manage allocations
        response = self.client.get(reverse('hr:manage_allocations'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

        # Manage holidays
        response = self.client.get(reverse('hr:manage_holidays'))
        self.assertRedirects(response, reverse('hr:my_attendance'))

        # Quick update attendance
        response = self.client.post(
            reverse('hr:quick_update_attendance'),
            data=json.dumps({'employee_id': self.employee.id, 'status': 'PRESENT'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_regular_user_leave_balance_only_shows_self(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('hr:leave_balance'))
        self.assertEqual(response.status_code, 200)
        data = response.context['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['user'], self.employee)

    def test_hr_admin_leave_balance_shows_all_employees(self):
        self.client.force_login(self.hr_user)
        response = self.client.get(reverse('hr:leave_balance'))
        self.assertEqual(response.status_code, 200)
        data = response.context['data']
        self.assertGreaterEqual(len(data), 2)

    def test_regular_user_can_view_own_attendance_and_apply_leave(self):
        self.client.force_login(self.employee)

        # View attendance history
        response = self.client.get(reverse('hr:attendance_history'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['employee'], self.employee)

        # Attempting to view another user's attendance forces self
        response = self.client.get(reverse('hr:employee_attendance_history', kwargs={'user_id': self.other_employee.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['employee'], self.employee)

        # Can access apply leave
        response = self.client.get(reverse('hr:apply_leave'))
        self.assertEqual(response.status_code, 200)
