from django.urls import path
from . import views, search_views, document_link_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dashboard/drill-down/', views.dashboard_drilldown, name='dashboard_drilldown'),
    path('sales-dashboard/', views.sales_dashboard, name='sales_dashboard'),
    path('api/sales-dashboard/', views.sales_dashboard_api, name='sales_dashboard_api'),
    path('api/sales-tracking/', views.sales_tracking_api, name='sales_tracking_api'),
    path('system-logs/unlock/', views.LogUnlockView.as_view(), name='log_unlock'),
    path('system-logs/', views.SystemActivityLogView.as_view(), name='system_logs'),
    
    # Health Check API
    path('api/health/', views.health_check, name='health_check'),
    path('health/', views.health_check, name='health_check_root'),
    
    # Global Search API
    path('api/global-search/', search_views.global_search, name='global_search'),
    
    # Document Linking API
    path('api/document-links/create/', document_link_views.create_document_link, name='create_document_link'),
    path('api/document-links/<int:link_id>/delete/', document_link_views.delete_document_link, name='delete_document_link'),
    path('api/document-links/unlink/', document_link_views.unlink_document, name='unlink_document'),
    path('api/document-links/search/', document_link_views.search_linkable_documents, name='search_linkable_documents'),
]
