import core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="gstin",
            field=models.CharField(
                blank=True,
                max_length=15,
                null=True,
                validators=[core.validators.validate_gstin],
            ),
        ),
        migrations.AlterField(
            model_name="contact",
            name="pan",
            field=models.CharField(
                blank=True,
                max_length=10,
                null=True,
                validators=[core.validators.validate_pan],
            ),
        ),
    ]

