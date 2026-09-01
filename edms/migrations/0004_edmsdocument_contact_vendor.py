import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0009_alter_contact_options_and_more'),
        ('edms', '0003_add_party_name_to_edms_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='edmsdocument',
            name='contact_vendor',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked contact from Customer/Supplier master',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='edms_documents',
                to='contacts.contact',
                verbose_name='Vendor / Customer',
            ),
        ),
    ]
