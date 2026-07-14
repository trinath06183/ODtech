from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="selling_price",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=15),
        ),
    ]

