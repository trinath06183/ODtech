from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0033_add_created_by_to_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='quotation_asked_by',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Quotation Asked By'),
        ),
    ]
