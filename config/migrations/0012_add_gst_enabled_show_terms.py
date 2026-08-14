from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("config", "0011_companyprofile_default_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="gst_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, GST columns will be pre-checked ON for all new documents.",
                verbose_name="Enable GST by Default",
            ),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="show_terms",
            field=models.BooleanField(
                default=True,
                help_text="When disabled, Terms and Conditions section will not appear on printed documents.",
                verbose_name="Show Terms and Conditions on Print",
            ),
        ),
    ]
