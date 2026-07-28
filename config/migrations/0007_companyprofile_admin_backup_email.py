from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('config', '0006_companyprofile_seq_chl_companyprofile_seq_crn_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='admin_backup_email',
            field=models.EmailField(blank=True, help_text='Email address to receive daily database backups.', max_length=254, null=True, verbose_name='Admin Backup Email'),
        ),
    ]
