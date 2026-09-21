from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_billofmaterials_assemblyworkorder_bomitem'),
    ]

    operations = [
        migrations.DeleteModel(
            name='BOMItem',
        ),
        migrations.DeleteModel(
            name='AssemblyWorkOrder',
        ),
        migrations.DeleteModel(
            name='BillOfMaterials',
        ),
    ]
