from django.db import migrations

def cleanup_non_note_original_invoices(apps, schema_editor):
    Document = apps.get_model('documents', 'Document')
    Document.objects.exclude(type__in=['CRN', 'DBN']).filter(
        original_invoice_number__isnull=False
    ).update(
        original_invoice_number=None,
        original_invoice_date=None,
        note_reason=None
    )

def reverse_cleanup(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0046_document_adjusted_amount_document_is_adjusted_and_more'),
    ]

    operations = [
        migrations.RunPython(cleanup_non_note_original_invoices, reverse_cleanup),
    ]

