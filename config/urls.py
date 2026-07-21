from django.urls import path
from . import views

urlpatterns = [
    path('', views.settings_view, name='settings'),
    path('documents/', views.company_docs_list, name='company_docs_list'),
    path('documents/folder/new/', views.company_folder_create, name='company_folder_create_root'),
    path('documents/folder/<int:pk>/', views.company_folder_view, name='company_folder_view'),
    path('documents/folder/<int:parent_pk>/new/', views.company_folder_create, name='company_folder_create'),
    path('documents/folder/<int:pk>/delete/', views.company_folder_delete, name='company_folder_delete'),
    path('documents/upload/', views.company_docs_upload, name='company_docs_upload_root'),
    path('documents/folder/<int:folder_pk>/upload/', views.company_docs_upload, name='company_docs_upload'),
    path('documents/<int:pk>/delete/', views.company_docs_delete, name='company_docs_delete'),

    # Backup & Restore Routes
    path('backup/', __import__('config.views_backup', fromlist=['']).backup_manager_view, name='backup_manager'),
    path('backup/create/', __import__('config.views_backup', fromlist=['']).backup_create_view, name='backup_create'),
    path('backup/download/<str:filename>/', __import__('config.views_backup', fromlist=['']).backup_download_view, name='backup_download'),
    path('backup/restore/', __import__('config.views_backup', fromlist=['']).backup_restore_view, name='backup_restore'),
]
