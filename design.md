# ODtech ERP — Design

> **Last Updated:** 2026-08-17

---

## 1. UI / Frontend Design

### Stack
- **Templates:** Django template engine (`.html` files in `/templates/`)
- **CSS:** Vanilla CSS (custom, no frameworks like Bootstrap/Tailwind)
- **JS:** Vanilla JavaScript with AJAX for dashboard and drilldown panels
- **Icons:** Emoji + custom SVG icons (no icon library dependency)
- **Charts:** Chart.js (Sales Dashboard revenue chart)

### Layout conventions
- Sidebar navigation; responsive for mobile via PWA
- Cards-based dashboard layout
- Slide-in drawer panels for drilldown details
- Flash messages via Django `messages` framework

### Template structure
```
templates/
├── base.html                   # Master layout (sidebar, nav, messages)
├── core/
│   ├── dashboard.html          # Main dashboard
│   ├── sales_dashboard.html    # Sales & Order Management dashboard
│   ├── activity_logs.html      # System activity log viewer
│   └── log_unlock.html         # Password re-auth for logs
├── tracker/                    # Order tracker templates
├── documents/                  # Document create/edit/preview templates
├── users/                      # Login, password reset, OTP templates
├── payments/                   # Payment & expense templates
├── inventory/                  # Stock & warranty templates
├── edms/                       # EDMS upload/browse templates
└── pwa/
    ├── manifest.json           # PWA manifest
    └── service-worker.js       # Service worker
```

---

## 2. Data Patterns

### Base model
All major models extend `core.TimeStampedModel`:
```python
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True
```

### Stock calculation
Stock is **never stored as a field**. It is always computed:
```python
StockTransaction.objects.filter(product=p).aggregate(total=Sum('quantity'))
```
This ensures a full audit trail and eliminates stale denormalized data.

### Document linking
`core.DocumentLink` is a **generic many-to-many** using `ContentType` + `source_id`/`target_id` strings.
This allows linking any two objects of any model type without schema changes.

### Financial calculations
All monetary values use `Decimal` (not `float`) to avoid floating-point precision errors.
The `money()` utility rounds to 2 decimal places consistently.

### Payment reconciliation
Payments link to documents via `document_ref` (a string matching `Document.number`).
`Document.get_all_linked_document_numbers()` traverses the full document lifecycle graph (BFS) to sum payments across linked documents (e.g. a payment on an Invoice is reflected on its parent Quotation).

---

## 3. API Design

### AJAX endpoints (JSON)
All dashboard data is loaded via AJAX `GET` endpoints returning `JsonResponse`:

| Endpoint | Purpose |
|----------|---------|
| `GET /dashboard/drill-down/?metric=&period=` | Slide-in drilldown panel data |
| `GET /api/sales-dashboard/?period=` | Full sales dashboard data |
| `GET /api/sales-tracking/?mode=&year=` | Monthly/yearly tracking table |
| `GET /api/global-search/?q=` | Global search across all entities |
| `POST /api/document-links/create/` | Create a document link |
| `DELETE /api/document-links/<id>/delete/` | Remove a document link |

### Period filter convention
- `today` — current date only
- `week` — last 7 days
- `month` — current calendar month
- `year` — current Indian FY (April 1 → March 31)

### Error responses
All API views return structured JSON on error:
```json
{ "error": "Human-readable message" }
```
HTTP 500 errors are logged via `logger.exception()` and return:
```json
{ "metric": "...", "period": "...", "data": [], "error": "An internal error occurred." }
```

---

## 4. Permission Pattern

### Three layers

**Layer 1 — Authentication:**
```python
@login_required
def my_view(request): ...
```

**Layer 2 — Role check:**
```python
@role_required('Admin', 'Managing Director')
def admin_only_view(request): ...
```

**Layer 3 — Section permission:**
```python
@require_permission('DOCUMENTS', 'write')
def create_document(request): ...
```

### Class-based views
For CBVs, use a helper method pattern (not inline string comparison):
```python
def _check_admin(self, request):
    return getattr(request.user, 'role', '') == 'Admin'

def get(self, request, *args, **kwargs):
    if not self._check_admin(request):
        messages.error(request, "Only Admins can view this.")
        return redirect('dashboard')
    ...
```

---

## 5. Logging Convention

All views use module-level loggers:
```python
import logging
logger = logging.getLogger(__name__)
```

**Rule:** Never use bare `except: pass`. Always log:
```python
except Exception:
    logger.exception("Descriptive message with context: %s", context_var)
```

---

## 6. Query Optimization Rules

1. **Use `select_related`** for ForeignKey traversals in list views
2. **Use `prefetch_related`** for reverse FK / M2M in list views
3. **Never query inside a loop** — use `annotate` + `values` to batch
4. **Dashboard KPIs** use a single `aggregate(t=Sum(...))` per metric — never iterate records
5. **Monthly data** uses `annotate(m=ExtractMonth(...)).values('m').annotate(cnt=Count('id'))` — one query per metric for all 12 months
6. **Top customers payments** are batched: one query for all invoices, one for all payments — never per customer

---

## 7. Document Number Generation

Document numbers follow a configurable prefix pattern (set in `config.CompanyProfile`).
Numbers are auto-generated sequentially and are **globally unique** (`unique=True` on `Document.number`).
Manual override is supported via `numbering_mode = 'manual'`.

---

## 8. Indian GST Rules

| Scenario | Tax applied |
|----------|------------|
| Customer in same state as company | CGST + SGST (split equally from `tax_total`) |
| Customer in different state | IGST (full `tax_total`) |
| `force_igst=True` on document | Always IGST regardless of state |
| `show_gst=False` on document | GST not shown on PDF |

State detection: `Contact.state` is compared to the company's state (`config.CompanyProfile`).

---

## 9. File Upload Rules

| Location | Model | Validator | Notes |
|----------|-------|-----------|-------|
| `product_docs/` | tracker.Product | `validate_safe_file` | Auto-compressed on save |
| `supplier_quotes/` | SupplierCostOption | `validate_safe_file` | Auto-compressed |
| `user_references/` | UserReferenceDocument | `validate_safe_file` | Notes/todo attachments |
| `expenses/receipts/` | payments.Expense | None | Receipt images |
| `warranty/` | WarrantyRegistration, WarrantyClaim | None | Warranty docs |
| `edms_storage/` | edms.EDMSDocument | Extension + MIME | Private; never direct-served |

---

## 10. Coding Conventions

- **Imports:** Top-level where possible; lazy imports inside functions only for circular import resolution
- **Money:** Always use `Decimal`, never `float`; use `core.utils.money()` for rounding
- **Date:** Use `timezone.localdate()` (not `datetime.date.today()`) for timezone-aware local date
- **UUIDs:** All tracker models use `UUIDField` as primary key for opaque, non-guessable IDs
- **Choices:** Use `TextChoices` or tuples at the model level; never hardcode status strings in views
- **Error handling:** `logger.exception(...)` always; never swallow exceptions silently
