# Generated for CompanyProfile show_inventory option
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('config', '0013_alter_companyprofile_show_terms'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='show_inventory',
            field=models.BooleanField(
                default=True,
                help_text='When disabled, the Inventory module will be hidden from navigation and dashboard.',
                verbose_name='Show Inventory Module'
            ),
        ),
    ]
