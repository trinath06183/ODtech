import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from edms.models import EDMSDocumentCategory

logger = logging.getLogger('edms.setup')
User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with initial EDMS categories and ensures all users have a valid role.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting EDMS setup...")

        # 1. Ensure all users have a valid EDMS role. If they have 'Accountant' or 'Staff',
        # we can upgrade them to 'Viewer' (or leave them if backward compatibility is preferred).
        # Actually, let's map 'Staff' to 'Viewer' to give them baseline access.
        users_updated = 0
        for user in User.objects.filter(role__in=['Staff', '']):
            user.role = 'Viewer'
            user.save(update_fields=['role'])
            users_updated += 1
            
        # Accountants might become 'Accounts'
        accounts_updated = 0
        for user in User.objects.filter(role='Accountant'):
            user.role = 'Accounts'
            user.save(update_fields=['role'])
            accounts_updated += 1
            
        self.stdout.write(self.style.SUCCESS(f"Updated {users_updated} 'Staff' users to 'Viewer' role."))
        self.stdout.write(self.style.SUCCESS(f"Updated {accounts_updated} 'Accountant' users to 'Accounts' role."))

        # 2. Setup Default Categories
        categories = [
            {'name': 'Finance & Accounts', 'icon': '💰', 'color': '#16a34a', 'order': 10},
            {'name': 'Invoices', 'icon': '🧾', 'color': '#2563eb', 'order': 20},
            {'name': 'Purchase Orders', 'icon': '🛍️', 'color': '#ea580c', 'order': 30},
            {'name': 'Human Resources', 'icon': '👥', 'color': '#db2777', 'order': 40},
            {'name': 'Engineering', 'icon': '⚙️', 'color': '#0284c7', 'order': 50},
            {'name': 'Legal & Contracts', 'icon': '⚖️', 'color': '#4f46e5', 'order': 60},
            {'name': 'Tender Documents', 'icon': '📜', 'color': '#ca8a04', 'order': 70},
            {'name': 'ISO Compliance', 'icon': '🛡️', 'color': '#059669', 'order': 80},
            {'name': 'Miscellaneous', 'icon': '📁', 'color': '#64748b', 'order': 99},
        ]

        for cat_data in categories:
            cat, created = EDMSDocumentCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={
                    'icon': cat_data['icon'],
                    'color': cat_data['color'],
                    'order': cat_data['order'],
                    'is_default': True,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created category: {cat.name}"))
            else:
                self.stdout.write(f"Category already exists: {cat.name}")

        self.stdout.write(self.style.SUCCESS("EDMS setup complete!"))
