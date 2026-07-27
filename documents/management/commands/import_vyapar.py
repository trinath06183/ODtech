"""
Management command: import_vyapar
Usage:
    py manage.py import_vyapar
    py manage.py import_vyapar --dry-run          # Preview without saving
    py manage.py import_vyapar --only contacts    # Import only contacts
    py manage.py import_vyapar --only products    # Import only products
    py manage.py import_vyapar --only invoices    # Import only invoices

SAFE: Does NOT delete, overwrite, or modify any existing ODtech records.
      Duplicates are detected by name/number and skipped automatically.
"""
import sqlite3
import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction


DB_PATH = r"d:\ODtech\Main_work\Deployment\vyp_extracted\database.db"
if not os.path.exists(DB_PATH):
    DB_PATH = "database.db"

# Vyapar txn_type → ODtech Document type
TXN_TYPE_MAP = {
    1:  'INV',   # Sale Invoice
    4:  'QTN',   # Estimate / Quotation
    2:  'PO',    # Purchase Bill
    5:  'PO',    # Purchase Order
    3:  'CRN',   # Sale Return / Credit Note
    20: 'INV',   # Sale with delivery challan
    18: 'CHL',   # Delivery Challan
}


class Command(BaseCommand):
    help = 'Safely import Vyapar backup data into ODtech (existing data is never modified)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview what would be imported without saving anything'
        )
        parser.add_argument(
            '--only', type=str, default='all',
            choices=['all', 'contacts', 'products', 'invoices'],
            help='Import only a specific category'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        only = options['only']

        if not os.path.exists(DB_PATH):
            self.stderr.write(self.style.ERROR(f"Database not found: {DB_PATH}"))
            return

        self.stdout.write(self.style.WARNING(
            f"\n{'[DRY RUN] ' if dry_run else ''}Starting Vyapar Import...\n"
        ))

        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row

        stats = {
            'contacts_created': 0, 'contacts_skipped': 0,
            'products_created': 0, 'products_skipped': 0,
            'invoices_created': 0, 'invoices_skipped': 0,
            'items_created': 0,
        }

        vyp_to_odtech_contact = {}
        vyp_to_odtech_product = {}

        # ================================================================
        # STEP 1: CONTACTS
        # ================================================================
        if only in ('all', 'contacts', 'invoices'):
            self.stdout.write(self.style.HTTP_INFO('\n--- Importing Contacts ---'))
            from contacts.models import Contact

            for party in con.execute("SELECT * FROM kb_names WHERE name_is_active = 1 ORDER BY name_id").fetchall():
                full_name = (party['full_name'] or '').strip()
                if not full_name:
                    continue

                name_type = party['name_type'] or 1
                contact_type = 'Customer' if name_type == 1 else ('Vendor' if name_type == 2 else 'Both')

                phone = (party['phone_number'] or '').strip()[:20] or None
                email = (party['email'] or '').strip() or None
                if email and '@' not in email:
                    email = None
                address = (party['address'] or '').strip() or None
                gstin = (party['name_gstin_number'] or '').strip() or None
                if gstin and len(gstin) != 15:
                    gstin = None

                existing = Contact.objects.filter(name__iexact=full_name).first()
                if existing:
                    stats['contacts_skipped'] += 1
                    vyp_to_odtech_contact[party['name_id']] = existing.id
                    continue

                if not dry_run:
                    with transaction.atomic():
                        c = Contact.objects.create(
                            name=full_name,
                            contact_type=contact_type,
                            phone=phone,
                            email=email,
                            address=address,
                            gstin=gstin,
                        )
                        vyp_to_odtech_contact[party['name_id']] = c.id
                stats['contacts_created'] += 1
                self.stdout.write(f"  + {full_name} ({contact_type})")

            self.stdout.write(
                f"  Done: {stats['contacts_created']} created, {stats['contacts_skipped']} skipped"
            )

        # ================================================================
        # STEP 2: PRODUCTS
        # ================================================================
        if only in ('all', 'products', 'invoices'):
            self.stdout.write(self.style.HTTP_INFO('\n--- Importing Products ---'))
            from inventory.models import Product

            units = {
                row['unit_id']: row['unit_name']
                for row in con.execute("SELECT unit_id, unit_name FROM kb_item_units").fetchall()
            }
            tax_codes = {
                row['tax_code_id']: row['tax_rate']
                for row in con.execute("SELECT tax_code_id, tax_rate FROM kb_tax_code").fetchall()
            }

            for item in con.execute("SELECT * FROM kb_items WHERE item_is_active = 1 ORDER BY item_id").fetchall():
                item_name = (item['item_name'] or '').strip()
                if not item_name:
                    continue

                sku = f"VYP-{item['item_id']}"
                existing = Product.objects.filter(sku=sku).first() or \
                           Product.objects.filter(name__iexact=item_name).first()

                if existing:
                    stats['products_skipped'] += 1
                    vyp_to_odtech_product[item['item_id']] = existing.id
                    continue

                # Resolve tax rate from IGST/CGST/SGST codes
                tax_rate = Decimal('18.00')
                if item['item_tax_id'] and item['item_tax_id'] in tax_codes:
                    raw = tax_codes[item['item_tax_id']]
                    # Vyapar stores component rates (9% CGST = 18% GST)
                    # If rate is a component, double it
                    if raw and raw <= 14:
                        tax_rate = Decimal(str(raw * 2))
                    elif raw:
                        tax_rate = Decimal(str(raw))

                if not dry_run:
                    with transaction.atomic():
                        p = Product.objects.create(
                            name=item_name[:255],
                            sku=sku[:100],
                            hsn_code=((item['item_hsn_sac_code'] or '').strip() or None),
                            tax_rate=tax_rate,
                            selling_price=Decimal(str(item['item_sale_unit_price'] or 0)),
                            purchase_price=Decimal(str(item['item_purchase_unit_price'] or 0)),
                            unit=units.get(item['base_unit_id'], 'Nos')[:50],
                            description=(item['item_description'] or '').strip() or None,
                        )
                        vyp_to_odtech_product[item['item_id']] = p.id
                stats['products_created'] += 1

            self.stdout.write(
                f"  Done: {stats['products_created']} created, {stats['products_skipped']} skipped"
            )

        # ================================================================
        # STEP 3: INVOICES / TRANSACTIONS
        # ================================================================
        if only in ('all', 'invoices'):
            self.stdout.write(self.style.HTTP_INFO('\n--- Importing Transactions ---'))
            from contacts.models import Contact
            from inventory.models import Product
            from documents.models import Document, DocumentItem

            # Reload contact/product maps in case this step runs alone
            if not vyp_to_odtech_contact:
                for party in con.execute("SELECT name_id, full_name FROM kb_names").fetchall():
                    c = Contact.objects.filter(name__iexact=(party['full_name'] or '').strip()).first()
                    if c:
                        vyp_to_odtech_contact[party['name_id']] = c.id

            if not vyp_to_odtech_product:
                for item in con.execute("SELECT item_id, item_name FROM kb_items").fetchall():
                    p = Product.objects.filter(sku=f"VYP-{item['item_id']}").first() or \
                        Product.objects.filter(name__iexact=(item['item_name'] or '').strip()).first()
                    if p:
                        vyp_to_odtech_product[item['item_id']] = p.id

            tax_codes = {
                row['tax_code_id']: row['tax_rate']
                for row in con.execute("SELECT tax_code_id, tax_rate FROM kb_tax_code").fetchall()
            }

            from datetime import date as dtdate

            for txn in con.execute("SELECT * FROM kb_transactions ORDER BY txn_id").fetchall():
                doc_type = TXN_TYPE_MAP.get(txn['txn_type'])
                if not doc_type:
                    stats['invoices_skipped'] += 1
                    continue

                ref_number = (txn['txn_ref_number_char'] or '').strip() or f"VYP-TXN-{txn['txn_id']}"

                if Document.objects.filter(number=ref_number).exists():
                    stats['invoices_skipped'] += 1
                    continue

                contact_id = vyp_to_odtech_contact.get(txn['txn_name_id'])
                if not contact_id:
                    name_row = con.execute(
                        "SELECT full_name FROM kb_names WHERE name_id = ?", (txn['txn_name_id'],)
                    ).fetchone()
                    party_name = (name_row['full_name'] if name_row else f'Party-{txn["txn_name_id"]}').strip()
                    if not dry_run:
                        c, _ = Contact.objects.get_or_create(
                            name=party_name,
                            defaults={'contact_type': 'Customer'}
                        )
                        contact_id = c.id
                    else:
                        contact_id = 1  # Placeholder for dry run

                lineitems = con.execute(
                    "SELECT * FROM kb_lineitems WHERE lineitem_txn_id = ?", (txn['txn_id'],)
                ).fetchall()

                if not lineitems:
                    stats['invoices_skipped'] += 1
                    continue

                try:
                    txn_date = dtdate.fromisoformat(txn['txn_date'].split(' ')[0])
                except Exception:
                    txn_date = dtdate.today()

                if not dry_run:
                    try:
                        with transaction.atomic():
                            doc = Document.objects.create(
                                type=doc_type,
                                number=ref_number,
                                numbering_mode='manual',
                                date=txn_date,
                                contact_id=contact_id,
                                status='Approved',
                                place_of_supply=txn['txn_place_of_supply'] or '21-Odisha',
                                subtotal=Decimal('0.00'),
                                tax_total=Decimal('0.00'),
                                grand_total=Decimal('0.00'),
                            )
                            
                            doc_subtotal = Decimal('0.00')
                            doc_taxtotal = Decimal('0.00')

                            for li in lineitems:
                                product_id = vyp_to_odtech_product.get(li['item_id'])
                                if not product_id:
                                    item_row = con.execute(
                                        "SELECT item_name FROM kb_items WHERE item_id = ?", (li['item_id'],)
                                    ).fetchone()
                                    iname = (item_row['item_name'] if item_row else f'Item-{li["item_id"]}').strip()
                                    p, _ = Product.objects.get_or_create(
                                        sku=f"VYP-{li['item_id']}",
                                        defaults={
                                            'name': iname[:255],
                                            'selling_price': Decimal(str(li['priceperunit'] or 0)),
                                        }
                                    )
                                    product_id = p.id

                                tax_rate_val = Decimal('18.00')
                                if li['lineitem_tax_id'] and li['lineitem_tax_id'] in tax_codes:
                                    r = tax_codes[li['lineitem_tax_id']]
                                    tax_rate_val = Decimal(str(r * 2 if r and r <= 14 else r or 18))
                                    
                                qty = Decimal(str(li['quantity'] or 1))
                                unit_price = Decimal(str(li['priceperunit'] or 0))
                                discount = Decimal(str(li['lineitem_discount_amount'] or 0))
                                
                                base = (qty * unit_price) - discount
                                tax_amt = base * (tax_rate_val / Decimal('100'))
                                
                                doc_subtotal += base
                                doc_taxtotal += tax_amt

                                DocumentItem.objects.create(
                                    document=doc,
                                    product_id=product_id,
                                    quantity=qty,
                                    unit_price=unit_price,
                                    tax_rate=tax_rate_val,
                                    discount=discount,
                                    tax_amount=tax_amt,
                                    total=base + tax_amt,
                                )
                                stats['items_created'] += 1
                                
                            doc.subtotal = doc_subtotal
                            doc.tax_total = doc_taxtotal
                            doc.grand_total = doc_subtotal + doc_taxtotal
                            doc.save(update_fields=['subtotal', 'tax_total', 'grand_total'])

                            stats['invoices_created'] += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  ERROR txn {txn['txn_id']}: {e}"))
                else:
                    stats['invoices_created'] += 1

            self.stdout.write(
                f"  Done: {stats['invoices_created']} created, {stats['invoices_skipped']} skipped"
            )

        con.close()

        self.stdout.write(self.style.SUCCESS(f"\n{'=' * 50}"))
        self.stdout.write(self.style.SUCCESS(f"{'[DRY RUN] ' if dry_run else ''}IMPORT COMPLETE"))
        self.stdout.write(self.style.SUCCESS(f"{'=' * 50}"))
        self.stdout.write(f"  Contacts  : {stats['contacts_created']} created / {stats['contacts_skipped']} skipped")
        self.stdout.write(f"  Products  : {stats['products_created']} created / {stats['products_skipped']} skipped")
        self.stdout.write(f"  Invoices  : {stats['invoices_created']} created / {stats['invoices_skipped']} skipped")
        self.stdout.write(f"  Line Items: {stats['items_created']} added")
        if dry_run:
            self.stdout.write(self.style.WARNING('\nNothing was saved. Remove --dry-run to apply.'))
