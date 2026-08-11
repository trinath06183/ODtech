from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0029_document_show_payment_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='currency',
            field=models.CharField(
                choices=[
                    ('INR', 'INR (₹) - Indian Rupee'),
                    ('USD', 'USD ($) - US Dollar'),
                    ('EUR', 'EUR (€) - Euro'),
                    ('GBP', 'GBP (£) - British Pound'),
                    ('AED', 'AED (د.إ) - UAE Dirham'),
                    ('SAR', 'SAR (ر.س) - Saudi Riyal'),
                    ('CAD', 'CAD (CA$) - Canadian Dollar'),
                    ('AUD', 'AUD (A$) - Australian Dollar'),
                    ('SGD', 'SGD (S$) - Singapore Dollar'),
                    ('JPY', 'JPY (¥) - Japanese Yen')
                ],
                default='INR',
                max_length=10,
                verbose_name='Currency'
            ),
        ),
    ]
