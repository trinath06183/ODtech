import django.db.models.deletion
from django.db import migrations, models


def populate_edms_ids(apps, schema_editor):
    EDMSDocument = apps.get_model('edms', 'EDMSDocument')
    docs = list(EDMSDocument.objects.order_by('created_at', 'id'))
    for idx, doc in enumerate(docs, start=1):
        doc.doc_seq = idx
        doc.document_id = f"EDMS{idx:08d}"
        doc.save(update_fields=['doc_seq', 'document_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('edms', '0004_edmsdocument_contact_vendor'),
    ]

    operations = [
        migrations.AddField(
            model_name='edmsdocument',
            name='doc_seq',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='edmsdocument',
            name='document_id',
            field=models.CharField(blank=True, db_index=True, help_text='Unique human-friendly document ID, e.g. EDMS00000001', max_length=30, null=True, verbose_name='Document ID'),
        ),
        migrations.RunPython(populate_edms_ids, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='edmsdocument',
            name='doc_seq',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='edmsdocument',
            name='document_id',
            field=models.CharField(blank=True, db_index=True, help_text='Unique human-friendly document ID, e.g. EDMS00000001', max_length=30, null=True, unique=True, verbose_name='Document ID'),
        ),
    ]
