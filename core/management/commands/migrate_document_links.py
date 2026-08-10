from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from core.models import DocumentLink
from documents.models import Document
from django.db import transaction

class Command(BaseCommand):
    help = 'Migrates legacy source_document ForeignKey relationships to the generic DocumentLink model'

    def handle(self, *args, **kwargs):
        document_ct = ContentType.objects.get_for_model(Document)
        
        documents_with_source = Document.objects.filter(source_document__isnull=False)
        count = documents_with_source.count()
        
        self.stdout.write(f"Found {count} documents with a source_document.")
        
        created = 0
        with transaction.atomic():
            for doc in documents_with_source:
                # doc.source_document is the original document (e.g., Quotation)
                # doc is the converted document (e.g., PI)
                # So source = doc.source_document, target = doc
                link, is_new = DocumentLink.objects.get_or_create(
                    source_type=document_ct,
                    source_id=doc.source_document_id,
                    target_type=document_ct,
                    target_id=doc.id,
                    link_type='converted',
                )
                if is_new:
                    created += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Successfully migrated {created} links into DocumentLink!"))
