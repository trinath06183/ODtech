# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('config', '0004_doc_number_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='allow_document_deletion',
            field=models.BooleanField(default=False, help_text='If disabled, the delete option for documents will be hidden and blocked.', verbose_name='Allow Document Deletion'),
        ),
    ]
