from django.urls import path
from . import views

urlpatterns = [
    path('gst/', views.gst_report, name='gst_report'),
    path('stock/', views.stock_summary, name='stock_summary'),
    path('financials/', views.financial_dashboard, name='financial_dashboard'),
    path('planning/', views.business_planning_dashboard, name='business_planning'),
]
