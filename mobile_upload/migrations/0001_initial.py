from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import mobile_upload.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MobileUploadSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('completed', 'Completed'), ('expired', 'Expired')],
                    default='pending',
                    max_length=20,
                )),
                ('uploaded_file', models.FileField(blank=True, null=True, upload_to=mobile_upload.models.mobile_upload_path)),
                ('original_filename', models.CharField(blank=True, max_length=255)),
                ('file_size', models.PositiveIntegerField(blank=True, null=True)),
                ('file_mime', models.CharField(blank=True, max_length=100)),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mobile_upload_sessions',
                    to='users.user',
                )),
            ],
            options={
                'verbose_name': 'Mobile Upload Session',
                'verbose_name_plural': 'Mobile Upload Sessions',
                'ordering': ['-created_at'],
            },
        ),
    ]
