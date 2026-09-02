from django.urls import path
from . import views

urlpatterns = [
    # List of all documents
    path('', views.document_list, name='document_list'),
    path('export/', views.document_export_csv, name='document_export_csv'),

    # New document form
    path('new/', views.create_document, name='create_document'),
    path('offline/', views.offline_document_view, name='document_offline'),
    
    # New quotation / invoice form
    path('cost-sheet/',    views.cost_sheet,       name='cost_sheet'),
    path('quotation/new/', views.create_quotation, name='create_quotation'),
    path('invoice/new/',   views.create_invoice,   name='create_invoice'),

    # Preview wrapper page
    path('<int:document_id>/',         views.document_preview,      name='document_detail'),
    path('<int:document_id>/preview/', views.document_preview,      name='document_preview'),
    path('<int:document_id>/change-status/', views.change_document_status, name='change_document_status'),

    # Raw HTML render (used inside iframe)
    path('<int:document_id>/html/',    views.document_html_preview,  name='document_html_preview'),

    # JSON data for sidebar preview card
    path('<int:document_id>/preview-data/', views.document_preview_data, name='document_preview_data'),

    # Edit document
    path('<int:document_id>/edit/',    views.edit_document,          name='edit_document'),

    # Delete document (Admin / Accountant only)
    path('<int:document_id>/delete/',  views.delete_document,        name='delete_document'),

    # Final PDF download
    path('<int:document_id>/pdf/',     views.generate_pdf,           name='generate_pdf'),

    # PDF Print (generates PDF server-side, embeds, auto-triggers print dialog)
    path('<int:document_id>/print/',   views.print_pdf,              name='print_pdf'),

    # Public Secure Document Viewer & PDF Download (Signed Token, No Login Needed)
    path('v/<str:token>/',             views.public_document_view,   name='public_document_view'),

    # Email document directly with PDF attachment API
    path('api/<int:document_id>/send-email/', views.email_document_api,  name='email_document_api'),

    # Document Bundle Transfer (Mode B: Export / Import .oddoc)
    path('<int:document_id>/export-bundle/', views.export_document_bundle_view, name='export_document_bundle'),
    path('import-bundle/',                   views.import_document_bundle_view, name='import_document_bundle'),

    # Product search API
    path('api/search-products/',       views.search_products,        name='search_products'),

    # Product create API
    path('api/create-product/',        views.create_product_api,     name='create_product_api'),

    # All products API (for browse modal)
    path('api/all-products/',          views.all_products_api,       name='all_products_api'),

    # Send document to tracking dashboard API
    path('api/<int:document_id>/send-to-tracker/', views.send_to_tracker_api, name='send_to_tracker_api'),

    # Next number API
    path('api/next-number/', views.get_next_number_api, name='get_next_number_api'),

    # PO Goods Receiving APIs
    path('api/<int:document_id>/po-items/', views.get_po_items_api, name='get_po_items_api'),
    path('api/<int:document_id>/receive-po-items/', views.receive_po_items_api, name='receive_po_items_api'),

    # Quick update Place of Supply API
    path('api/<int:document_id>/update-place-of-supply/', views.update_place_of_supply_api, name='update_place_of_supply_api'),

    # Link existing payment APIs
    path('api/<int:document_id>/search-payments/', views.search_payments_for_document_api, name='search_payments_for_document_api'),
    path('api/<int:document_id>/link-payment/', views.link_payment_to_document_api, name='link_payment_to_document_api'),
]
