from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Attendance
    path('attendance/mark/', views.mark_attendance, name='mark_attendance'),
    path('attendance/history/', views.my_attendance, name='attendance_history'),
    path('attendance/history/', views.my_attendance, name='my_attendance'),
    path('attendance/history/<int:user_id>/', views.attendance_history, name='employee_attendance_history'),
    path('attendance/report/', views.attendance_report, name='attendance_report'),
    path('attendance/report/', views.attendance_report, name='report'),

    # Leave — Employee self-service
    path('leave/apply/', views.apply_leave, name='apply_leave'),
    path('leave/<uuid:leave_id>/cancel/', views.cancel_leave, name='cancel_leave'),

    # Leave — HR management
    path('leave/requests/', views.leave_requests, name='leave_requests'),
    path('leave/<uuid:leave_id>/review/', views.review_leave, name='review_leave'),
    path('leave/balance/', views.leave_balance, name='leave_balance'),

    # Allocations & Holidays
    path('allocations/', views.manage_allocations, name='manage_allocations'),
    path('holidays/', views.manage_holidays, name='manage_holidays'),
    path('holidays/<int:holiday_id>/delete/', views.delete_holiday, name='delete_holiday'),
]
