from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0040_document_eway_bill_file_document_eway_bill_not_required'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstallationCertificate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_installation', models.DateField(verbose_name='Date of Installation')),
                ('installed_by', models.CharField(max_length=255, verbose_name='Installed By (Technician)')),
                ('inspected_by', models.CharField(blank=True, max_length=255, null=True, verbose_name='Inspected / Supervised By')),
                ('place_of_installation', models.CharField(blank=True, max_length=255, null=True, verbose_name='Place of Installation')),
                ('remarks', models.TextField(blank=True, null=True, verbose_name='Remarks / Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='installation_certificate',
                    to='documents.document',
                    verbose_name='Source Document',
                )),
            ],
            options={
                'verbose_name': 'Installation Certificate',
                'verbose_name_plural': 'Installation Certificates',
            },
        ),
    ]
