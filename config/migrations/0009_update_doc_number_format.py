from django.db import migrations, models

def update_company_format(apps, schema_editor):
    CompanyProfile = apps.get_model('config', 'CompanyProfile')
    CompanyProfile.objects.filter(doc_number_format='OD-{FY}-{MM}-{N}').update(doc_number_format='OD-{TYPE}-{FY}-{MM}-{N}')

class Migration(migrations.Migration):

    dependencies = [
        ('config', '0008_add_header_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='companyprofile',
            name='doc_number_format',
            field=models.CharField(
                choices=[
                    ('OD-{FY}-{MM}-{N}', 'OD-26-07-285  (FY + Month + S.No.)'),
                    ('OD-{TYPE}-{FY}-{MM}-{N}', 'OD-INV-26-07-285  (Type + FY + Month + S.No.)'),
                    ('OD-{TYPE}-{FYFY}-{MM}-{N}', 'OD-INV-2627-07-285  (Type + Full FY + Month + S.No.)')
                ],
                default='OD-{TYPE}-{FY}-{MM}-{N}',
                max_length=40
            ),
        ),
        migrations.RunPython(update_company_format, reverse_code=migrations.RunPython.noop),
    ]
