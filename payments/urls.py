from django.urls import path
from . import views

urlpatterns = [
    path('', views.payment_list, name='payment_list'),
    path('new/', views.payment_create, name='payment_create'),
    path('<int:payment_id>/delete/', views.payment_delete, name='payment_delete'),
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/new/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('expenses/<int:pk>/approve/<str:status>/', views.expense_approve, name='expense_approve'),
    path('expenses/<int:pk>/mark_paid/', views.expense_mark_paid, name='expense_mark_paid'),
    path('api/employee-codes/', views.employee_code_autocomplete, name='employee_code_autocomplete'),
]
