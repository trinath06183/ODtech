from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0042_installationcertificate_working_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationcertificate',
            name='custom_certificate_number',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Certificate Number'),
        ),
        migrations.AddField(
            model_name='installationcertificate',
            name='company_contact',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Company Contact Number'),
        ),
        migrations.AddField(
            model_name='installationcertificate',
            name='company_email',
            field=models.CharField(blank=True, max_length=150, null=True, verbose_name='Company Email ID'),
        ),
        migrations.AddField(
            model_name='installationcertificate',
            name='company_address',
            field=models.TextField(blank=True, null=True, verbose_name='Company Header Address'),
        ),
    ]
