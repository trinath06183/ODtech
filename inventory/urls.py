from django.urls import path
from . import views

urlpatterns = [
    path('',                              views.inventory_list,   name='inventory_list'),
    path('export/',                       views.inventory_export_csv, name='inventory_export_csv'),
    path('product/add/',                  views.product_create,   name='product_create'),
    path('product/<int:product_id>/edit/',   views.product_edit,  name='product_edit'),
    path('product/<int:product_id>/delete/', views.product_delete, name='product_delete'),
    path('product/<int:product_id>/adjust-stock/', views.adjust_stock, name='adjust_stock'),
    path('product/<int:product_id>/linked-bills/', views.get_product_linked_bills_api, name='get_product_linked_bills_api'),
    path('warranty/',                     views.warranty_tracker, name='warranty_tracker'),

    # -- Warranty Portal (public) --
    path('warranty/register/',            views.warranty_register,         name='warranty_register'),
    path('warranty/register/success/',    views.warranty_register_success, name='warranty_register_success'),
    path('warranty/claim/',               views.warranty_claim,            name='warranty_claim'),
    path('warranty/claim/success/<str:claim_number>/', views.warranty_claim_success, name='warranty_claim_success'),
    path('warranty/claim/recover/',       views.warranty_claim_recover,    name='warranty_claim_recover'),
    path('warranty/status/',              views.warranty_claim_status,     name='warranty_claim_status'),

    # -- Warranty Admin (internal) --
    path('warranty/admin/',                               views.warranty_admin_list,             name='warranty_admin_list'),
    path('warranty/admin/<int:claim_id>/status/',         views.warranty_admin_update_status,    name='warranty_admin_update_status'),
    path('warranty/admin/registration/<int:reg_id>/edit/', views.warranty_admin_edit_registration, name='warranty_admin_edit_registration'),

    # -- Bill of Materials (BOM) --
    path('bom/',                               views.bom_list,               name='bom_list'),
    path('bom/new/',                           views.bom_create,             name='bom_create'),
    path('bom/<int:bom_id>/edit/',             views.bom_edit,               name='bom_edit'),
    path('bom/<int:bom_id>/delete/',           views.bom_delete,             name='bom_delete'),
    path('api/bom/<int:bom_id>/details/',      views.api_bom_details,        name='api_bom_details'),

    # -- Assembly Work Orders --
    path('work-orders/',                       views.workorder_list,         name='workorder_list'),
    path('work-orders/new/',                   views.workorder_create,       name='workorder_create'),
    path('work-orders/<int:wo_id>/',           views.workorder_detail,       name='workorder_detail'),
    path('work-orders/<int:wo_id>/complete/',  views.workorder_complete,     name='workorder_complete'),
    path('work-orders/<int:wo_id>/status/',    views.workorder_status_update, name='workorder_status_update'),
]
