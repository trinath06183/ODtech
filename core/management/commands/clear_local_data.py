from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Clears all transactional data from local database while preserving tables and user accounts.'

    def handle(self, *args, **options):
        self.stdout.write("Starting comprehensive local data cleanup...\n")

        # 1. Commercial Documents
        try:
            from documents.models import Document, DocumentItem
            cnt_items, _ = DocumentItem.objects.all()._raw_delete(DocumentItem.objects.all().db) if hasattr(DocumentItem.objects.all(), '_raw_delete') else (DocumentItem.objects.all().delete(), None)
            cnt_docs = Document.objects.count()
            Document.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"✓ Cleared Documents ({cnt_docs}) and Document Items."))
        except Exception:
            try:
                from documents.models import Document, DocumentItem
                DocumentItem.objects.all().delete()
                Document.objects.all().delete()
                self.stdout.write(self.style.SUCCESS("✓ Cleared Documents and Document Items."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠ Documents clear notice: {e}"))

        # 2. Tracker App Data (Child to Parent order)
        try:
            from tracker.models import (
                SupplierCostOption, ProductExpense, ProductBookmark, PriceApprovalRequest,
                InternalNote, Task, Product as TrackerProduct, Lot, Order, OrderExpense,
                AuditLog, ErrorLog, UserTodo, UserNote, UserReferenceDocument
            )
            UserReferenceDocument.objects.all().delete()
            UserTodo.objects.all().delete()
            UserNote.objects.all().delete()
            SupplierCostOption.objects.all().delete()
            ProductExpense.objects.all().delete()
            ProductBookmark.objects.all().delete()
            PriceApprovalRequest.objects.all().delete()
            OrderExpense.objects.all().delete()
            InternalNote.objects.all().delete()
            Task.objects.all().delete()
            TrackerProduct.objects.all().delete()
            Lot.objects.all().delete()
            Order.objects.all().delete()
            AuditLog.objects.all().delete()
            ErrorLog.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Cleared Tracker Orders, Products, Lots, Expenses, and Supplier Options."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Tracker clear notice: {e}"))

        # 3. Payments & Expenses
        try:
            from payments.models import Payment, Expense
            p_cnt = Payment.objects.count()
            e_cnt = Expense.objects.count()
            Payment.objects.all().delete()
            Expense.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"✓ Cleared Payments ({p_cnt}) and Expenses ({e_cnt})."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Payments clear notice: {e}"))

        # 4. Inventory & Stock
        try:
            from inventory.models import Product as InvProduct, StockTransaction, WarrantyRegistration, WarrantyClaim
            WarrantyClaim.objects.all().delete()
            WarrantyRegistration.objects.all().delete()
            StockTransaction.objects.all().delete()
            InvProduct.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Cleared Inventory Products, Stock Transactions, and Warranties."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Inventory clear notice: {e}"))

        # 5. EDMS Documents
        try:
            from edms.models import (
                EDMSDocument, EDMSDocumentVersion, EDMSDocumentAccess,
                EDMSAuditLog, EDMSDocumentDownload, EDMSNotification, EDMSSavedSearch
            )
            EDMSDocumentDownload.objects.all().delete()
            EDMSNotification.objects.all().delete()
            EDMSSavedSearch.objects.all().delete()
            EDMSAuditLog.objects.all().delete()
            EDMSDocumentAccess.objects.all().delete()
            EDMSDocumentVersion.objects.all().delete()
            EDMSDocument.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✓ Cleared EDMS Documents, Versions, and Audit Logs."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ EDMS clear notice: {e}"))

        # 6. Mobile Upload Sessions
        try:
            from mobile_upload.models import MobileUploadSession
            m_cnt = MobileUploadSession.objects.count()
            MobileUploadSession.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"✓ Cleared Mobile Upload Sessions ({m_cnt})."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Mobile upload clear notice: {e}"))

        # 7. Contacts / Customers / Vendors
        try:
            from contacts.models import Contact
            c_cnt = Contact.objects.count()
            Contact.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"✓ Cleared Contacts ({c_cnt})."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠ Contacts clear notice: {e}"))

        self.stdout.write(self.style.SUCCESS("\n🎉 Cleanup finished! All transactional data has been removed. All database tables & User accounts are preserved."))

