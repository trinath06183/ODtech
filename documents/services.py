from decimal import Decimal
import re

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.utils import financial_year, money, to_decimal
from inventory.services import StockService

from .models import Document, DocumentItem


class NumberingService:
    DEFAULT_PREFIXES = {
        "QTN": "QTN-",
        "INV": "INV-",
        "PRO": "PRO-",
        "CHL": "CHL-",
        "PO": "PO-",
        "CRN": "CRN-",
        "DBN": "DBN-",
    }

    CONFIG_FIELDS = {
        "QTN": "quotation_prefix",
        "INV": "invoice_prefix",
        "CHL": "challan_prefix",
        "PO": "po_prefix",
    }

    @classmethod
    def prefix_for(cls, document_type):
        default = cls.DEFAULT_PREFIXES.get(document_type, f"{document_type}-")
        config_field = cls.CONFIG_FIELDS.get(document_type)
        if not config_field:
            return default

        try:
            from config.models import CompanyProfile

            company = CompanyProfile.objects.first()
            return getattr(company, config_field, default) if company else default
        except Exception:
            return default

    @classmethod
    def generate_document_number(cls, document_type, document_date=None, exclude_doc_id=None):
        document_date = document_date or timezone.localdate()

        # Compute FY parts
        year = document_date.year
        if document_date.month < 4:
            start_year = year - 1
            end_year = year
        else:
            start_year = year
            end_year = year + 1
        fy_2  = str(start_year)[-2:]          # e.g. "26"
        fy_4  = f"{str(start_year)[-2:]}{str(end_year)[-2:]}"  # e.g. "2627"

        month_str = document_date.strftime("%m")

        # Read configured format and next sequence from CompanyProfile
        fmt = 'OD-{FY}-{MM}-{N}'  # default
        next_number = 1
        
        config_field_map = {
            'QTN': 'seq_qtn',
            'INV': 'seq_inv',
            'PRO': 'seq_pro',
            'CHL': 'seq_chl',
            'PO':  'seq_po',
            'CRN': 'seq_crn',
            'DBN': 'seq_dbn',
        }
        
        try:
            from config.models import CompanyProfile
            company = CompanyProfile.objects.first()
            if company:
                if company.doc_number_format:
                    fmt = company.doc_number_format
                    
                config_field = config_field_map.get(document_type)
                if config_field:
                    # Next number is exactly the sequence setting + 1
                    next_number = getattr(company, config_field, 0) + 1
        except Exception:
            pass

        # Guarantee strict uniqueness (n+1 loop)
        while True:
            candidate = (
                fmt
                .replace('{TYPE}', document_type)
                .replace('{FYFY}', fy_4)
                .replace('{FY}',   fy_2)
                .replace('{MM}',   month_str)
                .replace('{N}',    str(next_number))
            )
            qs = Document.objects.filter(number=candidate)
            if exclude_doc_id:
                qs = qs.exclude(id=exclude_doc_id)
            if not qs.exists():
                return candidate
            next_number += 1

    @classmethod
    def bump_sequence(cls, document_type):
        config_field_map = {
            'QTN': 'seq_qtn',
            'INV': 'seq_inv',
            'PRO': 'seq_pro',
            'CHL': 'seq_chl',
            'PO':  'seq_po',
            'CRN': 'seq_crn',
            'DBN': 'seq_dbn',
        }
        config_field = config_field_map.get(document_type)
        if not config_field:
            return

        try:
            from config.models import CompanyProfile
            company = CompanyProfile.objects.first()
            if company:
                current_val = getattr(company, config_field, 0)
                setattr(company, config_field, current_val + 1)
                company.save(update_fields=[config_field])
        except Exception:
            pass
class TaxService:
    COMPANY_STATE_TOKENS = {"odisha", "orissa", "21", "21-odisha"}

    @classmethod
    def is_igst(cls, contact):
        if contact and contact.gstin and len(contact.gstin) >= 2:
            state_code = contact.gstin[:2]
            return state_code not in ["21"]
        return False

    @staticmethod
    def calculate_line(quantity, rate, tax_rate, discount=0):
        quantity = to_decimal(quantity)
        rate = to_decimal(rate)
        tax_rate = to_decimal(tax_rate)
        discount = to_decimal(discount)

        taxable_amount = money((quantity * rate) - discount)
        tax_amount = money(taxable_amount * tax_rate / Decimal("100"))
        total = money(taxable_amount + tax_amount)
        return {
            "taxable_amount": taxable_amount,
            "tax_amount": tax_amount,
            "total": total,
        }

    @classmethod
    def calculate_document_totals(cls, items, show_gst=True):
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        grand_total = Decimal("0.00")

        for item in items:
            line = cls.calculate_line(
                item.get("qty", 0),
                item.get("rate", 0),
                item.get("tax", 0) if show_gst else 0,
                item.get("discount", 0),
            )
            subtotal += line["taxable_amount"]
            tax_total += line["tax_amount"]
            grand_total += line["total"]

        return {
            "subtotal": money(subtotal),
            "tax_total": money(tax_total),
            "grand_total": money(grand_total),
        }


class PDFService:
    TEMPLATE_MAP = {
        "QTN": "documents/quotation.html",
        "CHL": "documents/challan.html",
        "PO": "documents/purchase_order.html",
        "INV": "documents/invoice.html",
        "PRO": "documents/invoice.html",
    }

    @classmethod
    def template_for(cls, document_type):
        return cls.TEMPLATE_MAP.get(document_type, "documents/quotation.html")

    @staticmethod
    def asset_context(for_pdf=False):
        if for_pdf:
            static_base = settings.BASE_DIR / "static"
            return {
                "logo_url": (static_base / "img/logo.png").as_uri(),
                "stamp_url": (static_base / "img/stamp.png").as_uri(),
                "sign_url": (static_base / "img/sign.png").as_uri(),
                "phone_icon": (static_base / "img/phone.png").as_uri(),
                "email_icon": (static_base / "img/email.png").as_uri(),
                "location_icon": (static_base / "img/location.png").as_uri(),
            }
        else:
            return {
                "logo_url": "/static/img/logo.png",
                "stamp_url": "/static/img/stamp.png",
                "sign_url": "/static/img/sign.png",
                "phone_icon": "/static/img/phone.png",
                "email_icon": "/static/img/email.png",
                "location_icon": "/static/img/location.png",
            }

    @classmethod
    def render_html(cls, document, request=None, for_pdf=False):
        from config.models import CompanyProfile
        company = CompanyProfile.objects.first()
        context = {
            "doc": document,
            "is_pdf": for_pdf,
            "header_address": getattr(company, 'header_address', '') or '',
            **cls.asset_context(for_pdf=for_pdf)
        }
        return render_to_string(cls.template_for(document.type), context, request=request)

    @classmethod
    def render_pdf(cls, document, request=None):
        import weasyprint

        html_string = cls.render_html(document, request=request, for_pdf=True)
        html_doc = weasyprint.HTML(
            string=html_string,
            base_url=settings.BASE_DIR.as_uri() + "/",
        )

        # ── Step 1: Render at 50000pt tall to measure EXACT content height ──
        # We use a massive height so it definitely fits on 1 page without artificial breaks.
        measure_css = weasyprint.CSS(string="@page { size: 595pt 50000pt; margin: 0; }")
        doc_wp = html_doc.render(stylesheets=[measure_css])
        
        # Get the height of the root <html> element (which contains body and all content)
        page = doc_wp.pages[0]
        html_box = page._page_box.children[0]
        total_height_pt = html_box.height * 0.75
        total_width_pt  = page.width * 0.75

        # ── Step 2: Re-render with a custom @page height = content height ──
        # Add a small buffer so the footer's bottom edge isn't clipped.
        BOTTOM_BUFFER_PT = 5
        override_css = weasyprint.CSS(string=f"""
            @page {{
                size: {total_width_pt}pt {total_height_pt + BOTTOM_BUFFER_PT}pt;
                margin: 0;
            }}
        """)

        html_string2 = cls.render_html(document, request=request, for_pdf=True)
        return weasyprint.HTML(
            string=html_string2,
            base_url=settings.BASE_DIR.as_uri() + "/",
        ).write_pdf(
            stylesheets=[override_css],
        )


class DocumentService:
    @staticmethod
    def apportion_discount(discount_type, discount_value, items):
        import decimal
        from core.utils import to_decimal, money

        discount_value = to_decimal(discount_value)
        
        # Calculate gross bases
        gross_bases = []
        total_gross = decimal.Decimal('0.00')
        for item in items:
            qty = to_decimal(item.get('qty', 0))
            rate = to_decimal(item.get('rate', 0))
            gross = qty * rate
            gross_bases.append(gross)
            total_gross += gross

        if discount_type == 'fixed':
            if total_gross > 0:
                allocated_total = decimal.Decimal('0.00')
                for i, item in enumerate(items):
                    gross = gross_bases[i]
                    item_discount = money(discount_value * gross / total_gross)
                    item['discount'] = item_discount
                    allocated_total += item_discount
                
                diff = discount_value - allocated_total
                if diff != 0 and len(items) > 0:
                    max_idx = gross_bases.index(max(gross_bases))
                    items[max_idx]['discount'] += diff
            else:
                for item in items:
                    item['discount'] = decimal.Decimal('0.00')

        elif discount_type == 'percentage':
            for i, item in enumerate(items):
                gross = gross_bases[i]
                item['discount'] = money(gross * discount_value / decimal.Decimal('100.00'))

        elif discount_type in ['individual', 'individual_pct']:
            for item in items:
                item['discount'] = to_decimal(item.get('discount', 0))

        else:
            for item in items:
                item['discount'] = decimal.Decimal('0.00')

    @staticmethod
    @transaction.atomic
    def create_document(document_type, contact_id, items, **kwargs):
        terms = kwargs.get("terms_and_conditions")
        if not terms:
            terms = Document.get_default_terms(document_type)
        # Allow caller to specify an explicit invoice date; fall back to today
        invoice_date = kwargs.get("invoice_date") or None
        doc_date_kwargs = {"date": invoice_date} if invoice_date else {}

        is_auto_number = not bool(kwargs.get("number"))
        document = Document.objects.create(
            type=document_type,
            status=kwargs.get("status", "Draft"),
            number=kwargs.get("number") or NumberingService.generate_document_number(document_type),
            numbering_mode=kwargs.get("numbering_mode", "auto"),
            **doc_date_kwargs,
            contact_id=contact_id,
            project_name=kwargs.get("project_name") or None,
            site_address=kwargs.get("site_address") or None,
            eway_bill=kwargs.get("eway_bill") or None,
            eway_bill_date=kwargs.get("eway_bill_date") or None,
            po_reference_number=kwargs.get("po_reference_number") or None,
            po_date=kwargs.get("po_date") or None,
            place_of_supply=kwargs.get("place_of_supply", "21-Odisha"),
            transporter_details=kwargs.get("transporter_details", "Local Transportation"),
            vehicle_number=kwargs.get("vehicle_number") or None,
            transport_doc_no=kwargs.get("transport_doc_no") or None,
            transport_doc_date=kwargs.get("transport_doc_date") or None,
            transport_reason=kwargs.get("transport_reason", "Refilling only, No Commercial involvement."),
            terms_and_conditions=terms,
            show_gst=kwargs.get("show_gst", False),
            split_gst=kwargs.get("split_gst", False),
            force_igst=kwargs.get("force_igst", False),
            discount_type=kwargs.get("discount_type", "none"),
            discount_value=kwargs.get("discount_value", Decimal("0.00")),
            payment_milestones=kwargs.get("payment_milestones") or None,
            table_columns=kwargs.get("table_columns") or None,
            enable_warranty=kwargs.get("enable_warranty", False),
            shipping_address=kwargs.get("shipping_address") or None,
            repeat_header=kwargs.get("repeat_header", False),
            source_document=kwargs.get("source_document"),
        )
        DocumentService.replace_items(document, items)
        if is_auto_number:
            NumberingService.bump_sequence(document_type)
        return document

    @staticmethod
    @transaction.atomic
    def update_document(document, document_type, contact_id, items, **kwargs):
        if "numbering_mode" in kwargs:
            document.numbering_mode = kwargs.get("numbering_mode")
        
        if document.type != document_type:
            document.type = document_type
            if document.numbering_mode == 'auto':
                document.number = NumberingService.generate_document_number(
                    document_type,
                    kwargs.get("invoice_date") or document.date,
                    exclude_doc_id=document.id
                )
                NumberingService.bump_sequence(document_type)
        
        if document.numbering_mode == 'manual' and kwargs.get("number"):
            document.number = kwargs.get("number")

        document.contact_id = contact_id
        document.project_name = kwargs.get("project_name") or None
        document.site_address = kwargs.get("site_address") or None
        document.eway_bill = kwargs.get("eway_bill") or None
        if "eway_bill_date" in kwargs:
            document.eway_bill_date = kwargs.get("eway_bill_date") or None
        if "transporter_details" in kwargs:
            document.transporter_details = kwargs.get("transporter_details") or "Local Transportation"
        if "vehicle_number" in kwargs:
            document.vehicle_number = kwargs.get("vehicle_number") or None
        if "transport_doc_no" in kwargs:
            document.transport_doc_no = kwargs.get("transport_doc_no") or None
        if "transport_doc_date" in kwargs:
            document.transport_doc_date = kwargs.get("transport_doc_date") or None
        if "transport_reason" in kwargs:
            document.transport_reason = kwargs.get("transport_reason") or "Refilling only, No Commercial involvement."
        document.po_reference_number = kwargs.get("po_reference_number") or None
        document.po_date = kwargs.get("po_date") or None
        if "invoice_date" in kwargs and kwargs["invoice_date"]:
            document.date = kwargs["invoice_date"]
        if "place_of_supply" in kwargs:
            document.place_of_supply = kwargs.get("place_of_supply")
        if "terms_and_conditions" in kwargs:
            document.terms_and_conditions = kwargs.get("terms_and_conditions")
        if "show_gst" in kwargs:
            document.show_gst = kwargs.get("show_gst")
        if "split_gst" in kwargs:
            document.split_gst = kwargs.get("split_gst")
        if "force_igst" in kwargs:
            document.force_igst = kwargs.get("force_igst")
        if "discount_type" in kwargs:
            document.discount_type = kwargs.get("discount_type")
        if "discount_value" in kwargs:
            document.discount_value = kwargs.get("discount_value")
        if "payment_milestones" in kwargs:
            document.payment_milestones = kwargs.get("payment_milestones")
        if "table_columns" in kwargs:
            document.table_columns = kwargs.get("table_columns")
        if "enable_warranty" in kwargs:
            document.enable_warranty = kwargs.get("enable_warranty")
        if "shipping_address" in kwargs:
            document.shipping_address = kwargs.get("shipping_address") or None
        if "repeat_header" in kwargs:
            document.repeat_header = kwargs.get("repeat_header")
        document.save()
        document.items.all().delete()
        DocumentService.replace_items(document, items)
        return document

    @staticmethod
    def replace_items(document, items):
        valid_items = [item for item in items if item.get("product_id") or item.get("name")]
        
        # Apportion discount prior to total calculation
        DocumentService.apportion_discount(document.discount_type, document.discount_value, valid_items)
        
        totals = TaxService.calculate_document_totals(valid_items, show_gst=document.show_gst)
        from inventory.models import Product
        for item in valid_items:
            product_id = item.get("product_id")
            
            # Support Custom Line Items
            if not product_id:
                from inventory.models import Product
                from decimal import Decimal
                custom_product, _ = Product.objects.get_or_create(
                    sku="CUSTOM",
                    defaults={
                        "name": "Custom Line Item",
                        "tax_rate": Decimal("18.00"),
                        "selling_price": Decimal("0.00"),
                    }
                )
                product_id = custom_product.id
            
            item_name = item.get("name", "")
            item_description = item.get("description", "")
            part_number_val = item.get("part_number", "")
            
            # Fetch product HSN code if not explicitly provided
            hsn_val = item.get("hsn_code")
            if not hsn_val and product_id:
                try:
                    from inventory.models import Product
                    hsn_val = Product.objects.get(id=product_id).hsn_code or ""
                except Product.DoesNotExist:
                    pass

            line = TaxService.calculate_line(
                item.get("qty", 0),
                item.get("rate", 0),
                item.get("tax", 0) if document.show_gst else 0,
                item.get("discount", 0),
            )
            DocumentItem.objects.create(
                document=document,
                product_id=product_id,
                name=item_name,
                description=item_description,
                part_number=part_number_val,
                serial_number=item.get("serial_number", ""),
                has_warranty=item.get("has_warranty", False),
                model=item.get("model", ""),
                warranty_period=item.get("warranty_period", ""),
                warranty_start_date=item.get("warranty_start_date") or None,
                hsn_code=hsn_val,
                unit=item.get("unit"),
                quantity=to_decimal(item.get("qty", 0)),
                unit_price=to_decimal(item.get("rate", 0)),
                discount=to_decimal(item.get("discount", 0)),
                tax_rate=to_decimal(item.get("tax", 0)),
                tax_amount=line["tax_amount"],
                total=line["total"],
            )

        document.subtotal = totals["subtotal"]
        document.tax_total = totals["tax_total"]
        document.grand_total = totals["grand_total"]
        document.save(update_fields=["subtotal", "tax_total", "grand_total", "updated_at"])

    @staticmethod
    @transaction.atomic
    def convert_document(source_doc_id, target_type):
        source_doc = Document.objects.prefetch_related("items").get(id=source_doc_id)

        items = [
            {
                "product_id": item.product_id,
                "qty": str(item.quantity),
                "unit": item.unit,
                "rate": str(item.unit_price),
                "tax": str(item.tax_rate),
                "discount": str(item.discount),
                "discount_pct": "0.00",
                "serial_number": item.serial_number or "",
            }
            for item in source_doc.items.all()
        ]

        return DocumentService.create_document(
            target_type,
            source_doc.contact_id,
            items,
            project_name=source_doc.project_name,
            site_address=source_doc.site_address,
            eway_bill=source_doc.eway_bill,
            discount_type=source_doc.discount_type,
            discount_value=source_doc.discount_value,
        )

    @staticmethod
    @transaction.atomic
    def approve_document(doc_id):
        doc = Document.objects.select_for_update().get(id=doc_id)
        if doc.status == "Approved":
            return doc

        doc.status = "Approved"
        doc.save(update_fields=["status", "updated_at"])

        if doc.type == "INV":
            from inventory.models import StockTransaction
            from inventory.services import StockService
            if not StockTransaction.objects.filter(reference_document=doc.number).exists():
                for item in doc.items.select_related("product"):
                    if item.product_id:
                        StockService.create_transaction(
                            product_id=item.product_id,
                            transaction_type="OUT",
                            quantity=item.quantity,
                            reference_document=doc.number,
                        )
        return doc
