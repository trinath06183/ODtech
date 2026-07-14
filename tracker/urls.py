from django.urls import path
from . import views

app_name = 'tracker'

urlpatterns = [
    # Dashboard (Read)
    path('', views.dashboard_view, name='dashboard'),
    path('products/all/', views.individual_products_view, name='individual_products'),
    
    # Order CRUD
    path('order/create/', views.OrderCreateView.as_view(), name='order_create'),
    path('order/<uuid:order_id>/', views.order_detail_view, name='order_detail'),
    path('order/<uuid:pk>/update/', views.OrderUpdateView.as_view(), name='order_update'),
    path('order/<uuid:pk>/delete/', views.OrderDeleteView.as_view(), name='order_delete'),

    # Lot CRUD
    path('order/<uuid:order_id>/lot/add/', views.LotCreateView.as_view(), name='lot_create'),
    path('lot/<uuid:lot_id>/', views.lot_detail_view, name='lot_detail'),
    path('lot/<uuid:pk>/update/', views.LotUpdateView.as_view(), name='lot_update'),
    path('lot/<uuid:pk>/delete/', views.LotDeleteView.as_view(), name='lot_delete'),

    # Product CRUD
    path('order/<uuid:order_id>/product/add/', views.ProductCreateView.as_view(), name='product_create_order'),
    path('lot/<uuid:lot_id>/product/add/', views.ProductCreateView.as_view(), name='product_create_lot'),
    path('product/<uuid:product_id>/', views.product_detail_view, name='product_detail'),
    path('product/<uuid:product_id>/modal/', views.product_modal_detail_view, name='product_modal_detail'),
    path('product/<uuid:pk>/update/', views.ProductUpdateView.as_view(), name='product_update'),
    path('product/<uuid:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('product/<uuid:product_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),

    # Supplier Option CRUD (Inline creation/updating handled in product_detail)
    path('supplier/<uuid:pk>/delete/', views.SupplierOptionDeleteView.as_view(), name='supplier_delete'),

    # Bulk CSV Upload
    path('order/<uuid:order_id>/products/upload/', views.product_csv_upload_view, name='product_csv_upload_order'),
    path('lot/<uuid:lot_id>/products/upload/', views.product_csv_upload_view, name='product_csv_upload_lot'),
    path('products/sample-csv/', views.download_sample_csv, name='download_sample_csv'),

    # Bulk Actions
    path('order/<uuid:order_id>/products/bulk-move/', views.bulk_move_products, name='bulk_move_products'),
    path('order/<uuid:order_id>/products/bulk-delete/', views.bulk_delete_products, name='bulk_delete_products'),
    path('product/<uuid:product_id>/toggle-purchase/', views.toggle_purchase_view, name='toggle_purchase'),
    # Master Search & Intelligence
    path('api/master-search/', views.master_search_api, name='master_search_api'),
    path('intelligence/product/', views.product_intelligence_view, name='product_intelligence'),
    path('intelligence/buyer/', views.buyer_profile_view, name='buyer_profile'),
    path('intelligence/seller/', views.seller_profile_view, name='seller_profile'),
    
    # Kanban & Automation APIs
    path('api/order/<uuid:order_id>/status/', views.update_order_status_api, name='api_update_order_status'),
    path('api/product/<uuid:product_id>/inline-update/', views.inline_update_product_api, name='api_inline_update_product'),
    path('api/product/bulk-status/', views.bulk_update_product_status_api, name='api_bulk_update_product_status'),
    path('api/product/bulk-edit/', views.bulk_attribute_edit_api, name='api_bulk_attribute_edit'),
    path('api/product/bulk-add-supplier/', views.bulk_add_supplier_api, name='api_bulk_add_supplier'),
    path('api/product/bulk-selling-price/', views.bulk_update_selling_price_api, name='api_bulk_update_selling_price'),
    path('api/product/bulk-stages/', views.bulk_update_stages_api, name='api_bulk_update_stages'),
    path('api/product/<uuid:product_id>/stage/', views.api_update_product_stage, name='api_update_product_stage'),

    path('api/notes/add/', views.add_internal_note_api, name='api_add_internal_note'),
    path('api/notes/bulk-add/', views.bulk_add_internal_note_api, name='api_bulk_add_internal_note'),

    path('api/notes/<uuid:note_id>/edit/', views.edit_internal_note_api, name='api_edit_internal_note'),
    path('api/notes/<uuid:note_id>/delete/', views.delete_internal_note_api, name='api_delete_internal_note'),
    path('api/notification/<uuid:notification_id>/read/', views.mark_notification_read_api, name='api_mark_notification_read'),
    path('api/notification/mark-all-read/', views.mark_all_notifications_read_api, name='api_mark_all_notifications_read'),
    
    # Admin User Management
    path('users/', views.user_management_list, name='user_management_list'),
    path('users/create/', views.user_management_create, name='user_management_create'),
    path('users/<int:user_id>/edit/', views.user_management_edit, name='user_management_edit'),
    path('users/<int:user_id>/delete/', views.user_management_delete, name='user_management_delete'),
    path('users/<int:user_id>/reset-password/', views.user_management_reset_password, name='user_management_reset_password'),
    
    # Audit Log
    path('audit-logs/', views.audit_log_list, name='audit_log_list'),
    path('audit-logs/<uuid:log_id>/delete/', views.delete_audit_log, name='delete_audit_log'),
    path('my/activity/', views.user_activity_view, name='user_activity'),
    
    # User Profile
    path('profile/', views.user_profile, name='user_profile'),

    # Price Approval
    path('price-approval/<uuid:request_id>/approve/', views.approve_price_request, name='approve_price_request'),
    path('price-approval/<uuid:request_id>/reject/', views.reject_price_request, name='reject_price_request'),

    path('api/order/<uuid:order_id>/create-lot/', views.api_create_lot, name='api_create_lot'),
    path('api/order/<uuid:order_id>/reorder-products/', views.api_reorder_products, name='api_reorder_products'),
    path('api/product/<uuid:product_id>/audit-log/', views.api_product_audit_log, name='api_product_audit_log'),

    # Personal Notes API (private per-user)
    path('api/my/notes/', views.api_notes_list_create, name='api_notes_list_create'),
    path('api/my/notes/<uuid:note_id>/', views.api_note_detail, name='api_note_detail'),

    # Personal To-Do API (private per-user)
    path('api/my/todos/', views.api_todos_list_create, name='api_todos_list_create'),
    path('api/my/todos/<uuid:todo_id>/', views.api_todo_detail, name='api_todo_detail'),

    # System Backup and Restore
    path('api/reference-document/<uuid:doc_id>/delete/', views.api_delete_reference_document, name='api_delete_reference_document'),
    path('system/admin/backup/', views.system_admin_backup_view, name='system_admin_backup'),
    path('system/backup/', views.system_backup, name='system_backup'),
    path('system/restore/', views.system_restore, name='system_restore'),
]
 
