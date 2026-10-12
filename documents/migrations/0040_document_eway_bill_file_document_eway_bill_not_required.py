# Generated for Document.eway_bill_file and Document.eway_bill_not_required

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0039_document_skip_reminder'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='eway_bill_file',
            field=models.FileField(blank=True, null=True, upload_to='eway_bills/', verbose_name='E-Way Bill File'),
        ),
        migrations.AddField(
            model_name='document',
            name='eway_bill_not_required',
            field=models.BooleanField(default=False, verbose_name='E-Way Bill Not Required'),
        ),
    ]
