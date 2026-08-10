from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0028_document_eway_bill_date_document_transport_doc_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='show_payment_summary',
            field=models.BooleanField(default=True),
        ),
    ]
