from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('config', '0010_companyprofile_gst_api_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='default_currency',
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
                help_text='Default currency pre-selected when creating new documents.',
                max_length=10,
                verbose_name='Default Currency'
            ),
        ),
    ]
