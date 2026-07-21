from django.urls import path
from . import views

urlpatterns = [
    # Desktop: generate a new QR session (POST, login required)
    path('generate-session/',              views.generate_qr_session,    name='mobile_generate_session'),

    # Phone: view the upload page (GET, no login needed — token is the key)
    path('upload/<uuid:token>/',           views.mobile_upload_page,     name='mobile_upload_page'),

    # Phone: submit the file (POST, CSRF exempt — token is the key)
    path('upload/<uuid:token>/submit/',    views.mobile_upload_submit,   name='mobile_upload_submit'),

    # Desktop: check upload status (GET, login required)
    path('upload/<uuid:token>/status/',    views.check_upload_status,    name='mobile_upload_status'),
]
