from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0036_document_custom_tracking_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='exchange_rate',
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal('1.0000'),
                help_text='Exchange rate from document currency to INR on document date (1 Currency = X INR)',
                max_digits=12,
                verbose_name='Exchange Rate (to INR)'
            ),
        ),
    ]
