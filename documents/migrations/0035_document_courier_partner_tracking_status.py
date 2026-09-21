from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0034_document_quotation_asked_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='courier_partner',
            field=models.CharField(blank=True, default='OTHER', max_length=50, null=True, verbose_name='Courier / Carrier Partner'),
        ),
        migrations.AddField(
            model_name='document',
            name='tracking_status',
            field=models.CharField(blank=True, default='Booked', max_length=50, null=True, verbose_name='Tracking Status'),
        ),
    ]
