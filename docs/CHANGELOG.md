# ODtech ERP — CHANGELOG

All notable changes are documented here in reverse chronological order.

---

## [Phase 8] — 2026-08-18

### Features & Automation
- **Live Profit & Loss (P&L) Statement:**
  - Added dedicated Live P&L page at `/reporting/pl/` with JSON API at `/reporting/pl/api/`.
  - Computes complete income statement: Net Revenue (Gross Invoices $\pm$ Credit/Debit Notes) $\rightarrow$ COGS (Purchase Orders + EDMS Vendor Invoices) $\rightarrow$ Gross Profit & Margin $\rightarrow$ Operating Expenses (Daily & Fixed) $\rightarrow$ Net Profit & Margin.
  - Interactive 12-month bar+line trend chart and expense breakdown donut chart powered by Chart.js.
- **Kanban / Pipeline Board for Orders:**
  - Added visual pipeline board at `/tracker/kanban/` with drag-and-drop swimlanes (Open $\rightarrow$ Sourcing $\rightarrow$ Procured $\rightarrow$ Shipped $\rightarrow$ Closed).
  - Dragging cards dynamically updates order status in the background via `tracker:api_update_order_status` with toast notifications.
- **WhatsApp Share on Quotations & Invoices:**
  - Added "Share on WhatsApp" action button on document previews (`templates/documents/document_preview.html`).
  - Generates formatted `wa.me` links pre-filled with document number, type, party name, total amount in INR format, and direct PDF view link.
- **Daily Executive Morning Digest (09:00 AM IST):**
  - Added management command `morning_digest` (`core/management/commands/morning_digest.py`).
  - Scheduled daily via APScheduler at 09:00 AM IST. Sends a rich HTML executive summary of today's, MTD, and FYTD revenue, order pipeline count, payments received, pending expense claims, and overdue invoices.
- **Automatic Financial Year (FY) Sequence Rollover:**
  - Added management command `fy_rollover` (`core/management/commands/fy_rollover.py`) with `--dry-run` safety flag.
  - Scheduled annually on April 1st at 00:01 AM IST to reset document sequence counters (`seq_qtn`, `seq_inv`, `seq_pro`, `seq_chl`, `seq_po`, `seq_crn`, `seq_dbn`) to `0` and notify the administrator.
- **Complete System Cloud Backup to Google Drive:**
  - Enhanced `backup_db` (`core/management/commands/backup_db.py`) to package both the PostgreSQL database dump and the entire uploaded media files folder into a single timestamped archive (`odtech_complete_backup_<timestamp>.tar.gz`).
  - Automatically uploads the complete archive to Google Drive with 7-backup retention management.
  - Added `auth_gdrive` helper command supporting both Service Account keys and headless OAuth 2.0 User authorization.

---

## [Phase 7] — 2026-08-17

### Features & Infrastructure
- **System Health Check API:** Added lightweight public health check endpoint at `/api/health/` and `/health/` returning HTTP 200/503 with database connectivity status and timestamp.
- **Automated Log Pruning:** Added management command `prune_logs` (`core/management/commands/prune_logs.py`) and scheduled daily at 02:00 AM IST via APScheduler to automatically delete `SystemActivityLog`, `ErrorLog`, and `AuditLog` records older than 90/180 days.

### Security
- **CRITICAL:** Re-enabled `CsrfViewMiddleware` (was commented out in `base.py`)
- **CRITICAL:** Removed insecure hardcoded `SECRET_KEY` fallback from `base.py` (replaced with dev-only placeholder; production requires env var)
- **CRITICAL:** Added `SECURE_HSTS_SECONDS = 31536000` to `base.py` — HSTS was declared but inactive without this value
- Configured `CSRF_COOKIE_HTTPONLY = False` in `production.py` (allows frontend JS/AJAX to read CSRF token) and `SESSION_COOKIE_HTTPONLY = True`.
- Added wildcard fallback support for `CSRF_TRUSTED_ORIGINS` (`.ngrok-free.dev`, `.ngrok.app`, `.ngrok.io`) in `production.py`.

### Bug Fixes
- **CRITICAL:** Fixed broken backup download links in automated emails (`core/management/commands/backup_db.py`) pointing to `/admin-config/backup/` instead of `/settings/backup/`.
- **CRITICAL:** Removed legacy raw SQL `ALTER TABLE` queries from `documents/apps.py` and `tracker/apps.py` `ready()` methods that caused database initialization warnings on every startup.
- **CRITICAL:** Fixed duplicate backup and payment reminder emails caused by multi-worker Gunicorn in production. Added inter-process file locking (`fcntl.flock`) in `users/scheduler.py` so only a single Gunicorn worker process initializes and runs scheduled background jobs.
- **CRITICAL:** Fixed onboarding profile completion failure where the First Name HTML input was incorrectly named `name="username"` instead of `name="first_name"`, causing the server-side check `request.POST.get('first_name')` to always be empty and reject the form with "All fields are required to complete onboarding."
- **CRITICAL:** Fixed `onboarding_view` and `logout_view` decorators from `@require_permission('USERS', 'read')` to `@login_required` (new users have no section permissions yet).
- **CRITICAL:** Fixed `dashboard_drilldown()` view which was building data but never returning a `JsonResponse` — every call returned `None`
- **CRITICAL:** Removed debug row (`'number': 'DEBUG'`) that was injected into every `orders_completed` API response, leaking internal query state to clients
- Replaced bare `except Exception: pass` blocks in dashboard view with `logger.exception(...)` so real errors are no longer silently swallowed

### Performance
- **Eliminated N+1 queries** in top-customers loop in `sales_dashboard_api()`: replaced per-customer invoice + payment queries with 2 bulk aggregation queries
- **Rewrote monthly tracking API** (`sales_tracking_api()`): replaced 70+ individual per-month queries with 6 bulk `annotate(ExtractMonth(...))` queries
- Added `db_index=True` to `SystemActivityLog.path` (migration: `core/migrations/0004_add_path_index_to_activity_log.py`)

### Code Quality
- Removed duplicate `from django.db.models import Sum as DbSum` import in `core/views.py`; top-level `Sum` import used everywhere
- Added module-level `logger = logging.getLogger(__name__)` to `core/views.py`
- Imported `role_required` at top of `core/views.py` (was unused after role check refactor)
- Refactored `LogUnlockView` inline `not ... == 'Admin'` string comparisons to a `_check_admin()` helper method
- Simplified `SystemActivityLogView.dispatch()` condition from `not ... == 'Admin'` to `!= 'Admin'`

### Deployment
- Applied migration `core.0004_add_path_index_to_activity_log` on production server
- Static files collected (159 files, 0 changed)
- `odtech.service` restarted with 3 gunicorn workers

---

## [Phase 6] — Prior to 2026-08-17

### Features Added
- Enterprise Document Management System (EDMS) with private file storage
- Main Dashboard with Month + FY KPI cards, drilldown panel
- Sales Dashboard with Chart.js revenue chart, top-10 customers, activity feed
- Sales Tracking table with monthly and yearly modes
- Mobile QR-code upload (`mobile_upload` app)
- PWA support (`manifest.json`, `service-worker.js`)
- `django-compressor` integration for CSS/JS minification in production
- Email notifications via SMTP for EDMS activity
- OTP-based access control for sensitive EDMS documents

---

## [Phase 5] — Prior to 2026-08-17

### Features Added
- Full Order Tracker (`tracker` app)
- `Order`, `Lot`, `Product` (tracker), `SupplierCostOption`, `PriceApprovalRequest`
- `Task` model with priority + assignment
- `InternalNote` for team collaboration
- `AuditLog` for immutable change history
- `ErrorLog` + `ErrorLoggingMiddleware` for 500 error capture
- `UserFieldVisibility` — per-user column visibility permissions
- `UserNote`, `UserTodo` — personal productivity tools
- `Notification` model + in-app notification bell
- `ProductExpense`, `OrderExpense` for per-product/order cost tracking
- Image compression on file uploads using OpenCV

---

## [Phase 4] — Prior to 2026-08-17

### Features Added
- `Payment` model with document reference linking
- Payment modes: Cash, Bank Transfer, Cheque, Credit Card, UPI
- `Expense` model with Daily/Fixed Cost categories and approval workflow
- Receivables calculation (invoiced minus paid)
- Aging buckets (30/60/90 day overdue) on dashboard

---

## [Phase 3] — Prior to 2026-08-17

### Features Added
- Commercial Documents app: QTN, PRO, INV, CHL, PO, CRN, DBN
- Multi-currency support (10 currencies)
- GST: CGST+SGST vs IGST with auto state detection
- Multiple discount types
- Amount-in-words generation (Indian numbering)
- PDF preview/print
- Document lifecycle linking via `DocumentLink`
- Configurable terms and conditions

---

## [Phase 2] — Prior to 2026-08-17

### Features Added
- `Contact` model (clients & vendors) with GST + state fields
- `Product` inventory catalogue with SKU, HSN code, reorder level
- `StockTransaction` ledger-style stock management
- `WarrantyRegistration` and `WarrantyClaim` with status workflow

---

## [Phase 1] — Prior to 2026-08-17

### Features Added
- Django project bootstrap with split settings
- Custom `User` model with role field
- Login, logout, OTP-based password reset
- `ActivityTrackingMiddleware` → `SystemActivityLog`
- `TimeStampedModel` abstract base
- gunicorn + systemd service deployment
- WhiteNoise static file serving
- `django-axes` brute-force protection
