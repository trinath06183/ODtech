from django.urls import path
from . import views

urlpatterns = [
    path('gst/', views.gst_report, name='gst_report'),
    path('stock/', views.stock_summary, name='stock_summary'),
    path('financials/', views.financial_dashboard, name='financial_dashboard'),
    path('planning/', views.business_planning_dashboard, name='business_planning'),
    path('pl/', views.profit_and_loss_view, name='profit_and_loss'),
    path('api/pl/', views.profit_and_loss_api, name='profit_and_loss_api'),
    path('statement/', views.statement_of_account_view, name='statement_of_account'),
    path('statement/v/<str:token>/', views.public_statement_view, name='public_statement_view'),
    path('daily-digest/', views.daily_digest_view, name='daily_digest'),
]
