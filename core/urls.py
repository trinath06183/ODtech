from django.urls import path
from . import views, search_views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('dashboard/drill-down/', views.dashboard_drilldown, name='dashboard_drilldown'),
    path('sales-dashboard/', views.sales_dashboard, name='sales_dashboard'),
    path('api/sales-dashboard/', views.sales_dashboard_api, name='sales_dashboard_api'),
    path('api/sales-tracking/', views.sales_tracking_api, name='sales_tracking_api'),
    path('system-logs/unlock/', views.LogUnlockView.as_view(), name='log_unlock'),
    path('system-logs/', views.SystemActivityLogView.as_view(), name='system_logs'),
    
    # Global Search API
    path('api/global-search/', search_views.global_search, name='global_search'),
]
