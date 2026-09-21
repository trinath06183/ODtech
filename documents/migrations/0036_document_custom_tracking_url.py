from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0035_document_courier_partner_tracking_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='custom_tracking_url',
            field=models.CharField(blank=True, max_length=500, null=True, verbose_name='Manual / Custom Tracking URL'),
        ),
    ]
