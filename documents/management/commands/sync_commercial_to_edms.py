"""
Management Command: sync_commercial_to_edms
============================================
Backfills EDMS records for all existing commercial documents
(Quotations, Invoices, Purchase Orders, Challans, etc.) that were
created before the auto-sync signal was installed.

Usage:
    py manage.py sync_commercial_to_edms

Options:
    --dry-run   Print what would be done without actually creating records.
"""

from django.core.management.base import BaseCommand
from documents.models import Document


class Command(BaseCommand):
    help = 'Sync all existing commercial documents into the EDMS module'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making DB changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN mode — no changes will be saved.\n'))

        from documents.signals import sync_commercial_doc_to_edms

        docs = Document.objects.select_related('contact').all()
        total = docs.count()
        self.stdout.write(f'Found {total} commercial document(s) to process…\n')

        created = updated = skipped = errors = 0

        for doc in docs:
            try:
                from edms.models import EDMSDocument
                exists = EDMSDocument.objects.filter(commercial_doc=doc).exists()

                if dry_run:
                    status = 'UPDATE' if exists else 'CREATE'
                    self.stdout.write(f'  [{status}] {doc.number} — {doc.contact.name if doc.contact_id else "No Contact"}')
                    if exists:
                        updated += 1
                    else:
                        created += 1
                else:
                    # Trigger the signal logic directly
                    sync_commercial_doc_to_edms(
                        sender=Document,
                        instance=doc,
                        created=not exists,
                    )
                    if exists:
                        updated += 1
                    else:
                        created += 1

            except Exception as exc:
                errors += 1
                self.stderr.write(
                    self.style.ERROR(f'  [ERROR] {doc.number}: {exc}')
                )

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS(f'✔ Created : {created}'))
        self.stdout.write(self.style.SUCCESS(f'✔ Updated : {updated}'))
        if errors:
            self.stdout.write(self.style.ERROR(f'✘ Errors  : {errors}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry-run complete — no records were saved.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nSync complete!'))
