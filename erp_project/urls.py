"""
URL configuration for erp_project project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('edms/', include('edms.urls', namespace='edms')),
    path('contacts/', include('contacts.urls')),
    path('documents/', include('documents.urls')),
    path('inventory/', include('inventory.urls')),
    path('users/',    include('users.urls')),
    path('settings/', include('config.urls')),
    path('payments/', include('payments.urls')),
    path('reports/',  include('reporting.urls')),
    path('reporting/', include('reporting.urls')),
    path('tracker/',  include('tracker.urls')),
    path('mobile/',   include('mobile_upload.urls')),
    
    # PWA Routes
    path('manifest.json', TemplateView.as_view(template_name='pwa/manifest.json', content_type='application/json'), name='manifest'),
    path('service-worker.js', TemplateView.as_view(template_name='pwa/service-worker.js', content_type='application/javascript'), name='service-worker'),

    path('', include('core.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

