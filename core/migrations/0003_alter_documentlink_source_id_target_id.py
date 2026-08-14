from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_documentlink'),
    ]
    operations = [
        migrations.AlterField(
            model_name='documentlink',
            name='source_id',
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='documentlink',
            name='target_id',
            field=models.CharField(db_index=True, max_length=64),
        ),
    ]