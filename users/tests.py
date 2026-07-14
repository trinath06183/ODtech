from django.test import TestCase
from django.urls import reverse
from users.models import User

class AuthenticationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_user',
            password='password123',
            role='Admin',
            email='admin@example.com'
        )
        self.staff = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='Staff',
            email='staff@example.com'
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_login_authenticated_redirects(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_successful(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin_user',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin_user',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        # Check that error is in messages
        messages = list(response.context['messages'])
        self.assertTrue(any('Invalid username or password' in str(m) for m in messages))

    def test_logout_view(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))


class UserManagementRBACConstraintTests(TestCase):
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
        self.target_user = User.objects.create_user(
            username='test_user',
            password='password123',
            role='Staff'
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('user_list'))
        self.assertRedirects(response, '/users/login/?next=/users/')

    def test_admin_can_access_user_list(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/user_list.html')

    def test_staff_cannot_access_user_list(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('user_list'))
        # Should redirect to dashboard with access denied error
        self.assertRedirects(response, reverse('dashboard'))

    def test_admin_can_create_user(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('user_create'), {
            'username': 'new_user',
            'email': 'new@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'Accountant',
            'password': 'password123',
            'is_active': 'on'
        })
        self.assertRedirects(response, reverse('user_list'))
        self.assertTrue(User.objects.filter(username='new_user').exists())

    def test_staff_cannot_create_user(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('user_create'), {
            'username': 'new_user',
            'email': 'new@example.com',
            'role': 'Accountant',
            'password': 'password123',
            'is_active': 'on'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(User.objects.filter(username='new_user').exists())

    def test_admin_can_edit_user(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('user_edit', args=[self.target_user.id]), {
            'email': 'updated@example.com',
            'first_name': 'Updated',
            'last_name': 'Name',
            'role': 'Accountant',
            'is_active': 'on',
            'password': '' # no password change
        })
        self.assertRedirects(response, reverse('user_list'))
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.email, 'updated@example.com')
        self.assertEqual(self.target_user.role, 'Accountant')

    def test_staff_cannot_edit_user(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('user_edit', args=[self.target_user.id]), {
            'email': 'updated@example.com',
            'role': 'Accountant',
            'is_active': 'on'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_admin_cannot_delete_self(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('user_delete', args=[self.admin.id]))
        self.assertRedirects(response, reverse('user_list'))
        self.assertTrue(User.objects.filter(id=self.admin.id).exists())

    def test_admin_can_delete_user(self):
        self.client.login(username='admin_user', password='password123')
        response = self.client.post(reverse('user_delete', args=[self.target_user.id]))
        self.assertRedirects(response, reverse('user_list'))
        self.assertFalse(User.objects.filter(id=self.target_user.id).exists())

    def test_staff_cannot_delete_user(self):
        self.client.login(username='staff_user', password='password123')
        response = self.client.post(reverse('user_delete', args=[self.target_user.id]))
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(User.objects.filter(id=self.target_user.id).exists())


class OnboardingAndVerificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_user',
            password='password123',
            role='Admin',
            email='admin@example.com'
        )
        self.client.login(username='admin_user', password='password123')

    def test_public_registration_removed(self):
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('register')

    def test_admin_user_creation_triggers_email_verification(self):
        from django.core import mail
        response = self.client.post(reverse('user_create'), {
            'username': 'new_staff',
            'email': 'new_staff@example.com',
            'first_name': 'Jane',
            'last_name': 'Smith',
            'role': 'Staff',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('user_list'))
        self.assertTrue(User.objects.filter(username='new_staff').exists())
        
        user = User.objects.get(username='new_staff')
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_onboarded)
        
        # Verify verification email sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Verify your email for ODtech ERP')

    def test_email_verification_successful_and_redirects_to_onboarding(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        user = User.objects.create_user(
            username='unverified_staff',
            password='password123',
            email='unverified@example.com',
            is_active=False,
            is_email_verified=False,
            is_onboarded=False
        )
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Logout admin and trigger verification link
        self.client.logout()
        response = self.client.get(reverse('verify_email', kwargs={'uidb64': uid, 'token': token}))
        
        # Should redirect to dashboard, which redirects to onboarding via middleware
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertFalse(user.is_onboarded)
        
        # Hitting dashboard redirects to onboarding
        dashboard_response = self.client.get(reverse('dashboard'))
        self.assertRedirects(dashboard_response, reverse('onboarding'))

    def test_onboarding_submission_completes_profile(self):
        user = User.objects.create_user(
            username='unonboarded_staff',
            password='password123',
            email='unonboarded@example.com',
            is_active=True,
            is_email_verified=True,
            is_onboarded=False
        )
        self.client.login(username='unonboarded_staff', password='password123')
        
        response = self.client.post(reverse('onboarding'), {
            'first_name': 'Arthur',
            'last_name': 'Dent',
            'designation': 'Reporter',
            'empid': 'EMP-42'
        })
        self.assertRedirects(response, reverse('dashboard'))
        
        user.refresh_from_db()
        self.assertTrue(user.is_onboarded)
        self.assertEqual(user.first_name, 'Arthur')
        self.assertEqual(user.last_name, 'Dent')
        self.assertEqual(user.designation, 'Reporter')
        self.assertEqual(user.empid, 'EMP-42')

    def test_onboarding_validation_requires_all_fields(self):
        user = User.objects.create_user(
            username='unonboarded_staff_2',
            password='password123',
            email='unonboarded2@example.com',
            is_active=True,
            is_email_verified=True,
            is_onboarded=False
        )
        self.client.login(username='unonboarded_staff_2', password='password123')
        
        response = self.client.post(reverse('onboarding'), {
            'first_name': 'Arthur',
            'last_name': '',  # missing last name
            'designation': 'Reporter',
            'empid': 'EMP-42'
        })
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('All fields are required to complete onboarding' in str(m) for m in messages))
        
        user.refresh_from_db()
        self.assertFalse(user.is_onboarded)



class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset_user',
            password='password123',
            email='reset@example.com'
        )

    def test_password_reset_page_renders(self):
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/password_reset_form.html')

    def test_password_reset_submission(self):
        from django.core import mail
        response = self.client.post(reverse('password_reset'), {
            'email': 'reset@example.com'
        })
        self.assertRedirects(response, reverse('password_reset_done'))
        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Password reset on ODtech ERP')

