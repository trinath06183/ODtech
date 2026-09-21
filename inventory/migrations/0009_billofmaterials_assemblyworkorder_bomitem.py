from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0008_warrantyclaim_status_reason'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillOfMaterials',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bom_number', models.CharField(help_text='e.g. BOM-2026-001', max_length=50, unique=True)),
                ('name', models.CharField(help_text='e.g. Standard MIG-250 Assembly Specification', max_length=255)),
                ('version', models.CharField(default='1.0', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('labor_cost', models.DecimalField(decimal_places=2, default=0.0, help_text='Direct labor cost per unit', max_digits=15)),
                ('overhead_cost', models.DecimalField(decimal_places=2, default=0.0, help_text='Overhead cost per unit', max_digits=15)),
                ('notes', models.TextField(blank=True, null=True)),
                ('finished_product', models.ForeignKey(help_text='Finished product manufactured or assembled', on_delete=django.db.models.deletion.CASCADE, related_name='boms', to='inventory.product')),
            ],
            options={
                'verbose_name': 'Bill of Materials',
                'verbose_name_plural': 'Bills of Materials',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='BOMItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity_required', models.DecimalField(decimal_places=4, help_text='Quantity required per 1 finished unit', max_digits=15)),
                ('unit', models.CharField(default='Nos', max_length=50)),
                ('scrap_percentage', models.DecimalField(decimal_places=2, default=0.0, help_text='Expected scrap/wastage %', max_digits=5)),
                ('notes', models.CharField(blank=True, max_length=255, null=True)),
                ('bom', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='inventory.billofmaterials')),
                ('component_product', models.ForeignKey(help_text='Raw material or sub-component item', on_delete=django.db.models.deletion.PROTECT, related_name='bom_usages', to='inventory.product')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='AssemblyWorkOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order_number', models.CharField(help_text='e.g. WO-2026-0001', max_length=50, unique=True)),
                ('quantity_to_produce', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('Draft', 'Draft'), ('Scheduled', 'Scheduled'), ('In Production', 'In Production'), ('Completed', 'Completed'), ('Cancelled', 'Cancelled')], default='Draft', max_length=20)),
                ('assigned_technician', models.CharField(blank=True, help_text='Technician or supervisor name', max_length=150, null=True)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('target_date', models.DateField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('serial_numbers_produced', models.TextField(blank=True, help_text='Comma or newline-separated serial numbers of completed units', null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('bom', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_orders', to='inventory.billofmaterials')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assembly_work_orders', to=settings.AUTH_USER_MODEL)),
                ('finished_product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_orders', to='inventory.product')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
