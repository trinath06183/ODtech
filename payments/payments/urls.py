from django.urls import path
from . import views

urlpatterns = [
    path('', views.payment_list, name='payment_list'),
    path('new/', views.payment_create, name='payment_create'),
    path('<int:payment_id>/delete/', views.payment_delete, name='payment_delete'),
]
