# Generated for Document.skip_reminder

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0038_alter_document_exchange_rate'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='skip_reminder',
            field=models.BooleanField(default=False, verbose_name='Skip Payment Reminder'),
        ),
    ]
