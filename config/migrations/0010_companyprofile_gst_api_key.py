from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('config', '0009_update_doc_number_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='gst_api_key',
            field=models.CharField(
                blank=True,
                help_text='Key for RapidAPI GST Insights service to auto-fetch party name and registered address.',
                max_length=255,
                null=True,
                verbose_name='GST API Key (RapidAPI)'
            ),
        ),
    ]
