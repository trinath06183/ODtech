from django.urls import path
from . import views

urlpatterns = [
    # List of all documents
    path('', views.document_list, name='document_list'),

    # New document form
    path('new/', views.create_document, name='create_document'),
    
    # New quotation / invoice form
    path('cost-sheet/',    views.cost_sheet,       name='cost_sheet'),
    path('quotation/new/', views.create_quotation, name='create_quotation'),
    path('invoice/new/',   views.create_invoice,   name='create_invoice'),

    # Preview wrapper page
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

    # Product search API
    path('api/search-products/',       views.search_products,        name='search_products'),

    # Product create API
    path('api/create-product/',        views.create_product_api,     name='create_product_api'),

    # All products API (for browse modal)
    path('api/all-products/',          views.all_products_api,       name='all_products_api'),
]
