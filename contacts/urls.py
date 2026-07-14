from django.urls import path
from . import views

urlpatterns = [
    # Contact CRUD
    path('', views.contact_list, name='contact_list'),
    path('new/', views.contact_create, name='contact_create'),
    path('<int:contact_id>/edit/', views.contact_edit, name='contact_edit'),
    path('<int:contact_id>/delete/', views.contact_delete, name='contact_delete'),
    path('<int:contact_id>/', views.contact_detail, name='contact_detail'),

    # Vendor quotes
    path('vendor-quotes/', views.vendor_quotes, name='vendor_quotes'),
    path('vendor-quotes/new/', views.vendor_quote_create, name='vendor_quote_create'),
    path('vendor-quotes/<int:quote_id>/edit/', views.vendor_quote_edit, name='vendor_quote_edit'),
    path('vendor-quotes/<int:quote_id>/delete/', views.vendor_quote_delete, name='vendor_quote_delete'),

    # API
    path('api/create-customer/', views.create_customer_api, name='create_customer_api'),
]
