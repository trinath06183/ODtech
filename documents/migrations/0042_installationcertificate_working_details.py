from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0041_installationcertificate'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationcertificate',
            name='working_details',
            field=models.TextField(blank=True, null=True, verbose_name='Working Details / Commissioning Scope'),
        ),
        migrations.AddField(
            model_name='installationcertificate',
            name='project_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Project Name'),
        ),
        migrations.AddField(
            model_name='installationcertificate',
            name='site_address',
            field=models.TextField(blank=True, null=True, verbose_name='Site Address'),
        ),
    ]
