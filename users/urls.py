from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/',      views.login_view,      name='login'),
    path('login/verify-otp/', views.login_verify_otp, name='login_verify_otp'),
    path('login/resend-otp/', views.login_resend_otp, name='login_resend_otp'),
    path('logout/',     views.logout_view,     name='logout'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('verify-email/<uidb64>/<token>/', views.verify_email_view, name='verify_email'),

    # OTP-based Password Reset (3-step flow)
    path('password-reset/',                       views.password_reset_request,     name='password_reset'),
    path('password-reset/verify-otp/',            views.password_reset_verify_otp,  name='password_reset_verify_otp'),
    path('password-reset/resend-otp/',            views.password_reset_resend_otp,  name='password_reset_resend_otp'),
    path('password-reset/set-password/',          views.password_reset_set_password, name='password_reset_set_password'),
    path('password-reset/complete/',              views.password_reset_complete,    name='password_reset_complete'),

    # User Management (Admin only)
    path('',                      views.user_list,   name='user_list'),
    path('create/',               views.user_create, name='user_create'),
    path('<int:user_id>/edit/',   views.user_edit,   name='user_edit'),
    path('<int:user_id>/delete/', views.user_delete, name='user_delete'),
]
