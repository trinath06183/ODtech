# ODtech ERP — Development Phases

> **Last Updated:** 2026-08-17

---

## Phase 1 — Foundation ✅ COMPLETE

**Goal:** Core Django project setup, authentication, and basic infrastructure.

- [x] Django project created with split settings (base / development / production)
- [x] Custom `User` model (`AbstractUser`) with role field
- [x] Login, logout, OTP-based password reset
- [x] `TimeStampedModel` abstract base class
- [x] `ActivityTrackingMiddleware` for POST/PUT/DELETE audit logging
- [x] `SystemActivityLog` model with admin-only view (password re-auth protected)
- [x] WhiteNoise static file serving
- [x] gunicorn + systemd deployment on Ubuntu

---

## Phase 2 — Contacts & Inventory ✅ COMPLETE

**Goal:** Core master data for all other modules.

- [x] `Contact` model (clients & vendors) with GST number, state, addresses
- [x] `Product` inventory catalogue with SKU, HSN code, tax rate, reorder level
- [x] `StockTransaction` ledger (IN/OUT/ADJUSTMENT)
- [x] Real-time stock calculation via aggregation
- [x] Low stock alerts (dashboard badge)
- [x] `WarrantyRegistration` and `WarrantyClaim` models + views

---

## Phase 3 — Commercial Documents ✅ COMPLETE

**Goal:** Full document generation lifecycle.

- [x] `Document` model: QTN, PRO, INV, CHL, PO, CRN, DBN
- [x] `DocumentItem` with tax calculation on save
- [x] Multi-currency support (10 currencies)
- [x] GST logic: CGST+SGST vs IGST based on contact state
- [x] Multiple discount types (none, global fixed/%, individual ₹/%)
- [x] Amount-in-words (Indian numbering for INR)
- [x] PDF preview/print view
- [x] Document status: Draft → Approved → Cancelled
- [x] `DocumentLink` generic many-to-many for lifecycle tracking
- [x] Document conversion (QTN → INV etc.) preserving source link
- [x] Configurable terms and conditions

---

## Phase 4 — Payments ✅ COMPLETE

**Goal:** Track money flow in and out.

- [x] `Payment` model linked to contact + document reference
- [x] Payment modes: Cash, Bank Transfer, Cheque, Credit Card, UPI
- [x] `Expense` model with Daily / Fixed Cost categories
- [x] Expense approval workflow (Pending → Approved → Rejected → Paid)
- [x] Receivables calculation (invoiced minus paid)
- [x] Aging buckets (30 / 60 / 90 day overdue)
- [x] Balance due calculation via document lifecycle graph traversal

---

## Phase 5 — Order Tracker ✅ COMPLETE

**Goal:** Full operational order management.

- [x] `Order` model with UUID PK, status, payment status
- [x] `Lot` grouping within orders
- [x] `Product` (tracker) with dual customer + supplier stage tracking
- [x] `SupplierCostOption` with multi-supplier comparison
- [x] `PriceApprovalRequest` workflow (below minimum margin threshold)
- [x] `Task` model with priority and assignment
- [x] `InternalNote` for team collaboration
- [x] `AuditLog` for immutable change history
- [x] `ErrorLog` + `ErrorLoggingMiddleware` for 500 error capture
- [x] `UserFieldVisibility` — per-user column visibility permissions
- [x] `UserNote` and `UserTodo` — personal productivity tools
- [x] `Notification` model + in-app notification bell
- [x] `ProductExpense` and `OrderExpense` for cost tracking
- [x] Image compression on file uploads (OpenCV)

---

## Phase 6 — EDMS & Dashboards ✅ COMPLETE

**Goal:** Enterprise document management and management visibility.

- [x] `EDMSDocument` with private storage (outside web root)
- [x] Category-based organization with access levels
- [x] OTP-based access for sensitive documents
- [x] Email notifications via SMTP
- [x] Main Dashboard with Month + FY KPI cards
- [x] Dashboard drilldown AJAX panel
- [x] Sales Dashboard with revenue chart, top customers, activity feed
- [x] Sales Tracking table (monthly + yearly mode)
- [x] Mobile QR-code upload (`mobile_upload`)
- [x] PWA support (`manifest.json`, `service-worker.js`)
- [x] `django-compressor` for CSS/JS minification

---

## Phase 7 — Security & Performance Hardening ✅ COMPLETE (2026-08-17)

**Goal:** Close security gaps and optimize query performance.

- [x] Re-enable CSRF middleware
- [x] Remove insecure `SECRET_KEY` fallback
- [x] Add `SECURE_HSTS_SECONDS = 31536000`
- [x] Add explicit `SESSION_COOKIE_HTTPONLY` and `CSRF_COOKIE_HTTPONLY`
- [x] Fix missing `return JsonResponse` in `dashboard_drilldown`
- [x] Remove debug row from `orders_completed` API response
- [x] Eliminate N+1 queries in top-customers loop (batch payment aggregation)
- [x] Rewrite monthly tracking API: 6 bulk queries vs 70+ individual
- [x] Replace bare `except: pass` with `logger.exception()`
- [x] Add `db_index=True` to `SystemActivityLog.path`
- [x] Remove duplicate `Sum as DbSum` import

---

## Phase 8 — Advanced Reporting & Enterprise Operations ✅ COMPLETE (2026-08-18)

**Goal:** Comprehensive financial reporting, operations tracking, and cloud automation.

- [x] **Live Profit & Loss (P&L) Statement:** Full Income Statement (/reporting/pl/) with Revenue, COGS, OpEx, Net Profit, and Chart.js 12-month trend
- [x] **Kanban Pipeline Board for Orders:** Drag-and-drop swimlane pipeline (/tracker/kanban/) with real-time status updates
- [x] **WhatsApp Share Link:** 1-click sharing of Quotations and Invoices with pre-formatted text and PDF link
- [x] **Daily Executive Morning Digest:** 09:00 AM IST scheduled email with daily/MTD/FYTD revenue, order pipeline, payments, and alerts
- [x] **Automatic FY Sequence Rollover:** Scheduled April 1st 00:01 AM sequence reset command with dry-run support
- [x] **Complete Cloud Backup to Google Drive:** Automated full package (.tar.gz with DB + media) sync to Google Drive with 7-backup retention

---

## Phase 9 — Tax Compliance & External Integrations 🔲 PLANNED

**Goal:** Automated compliance and third-party accounting handover.

- [ ] **GSTR-1 GST Return Export:** One-click B2B / B2C invoice data export matching GST portal Excel format
- [ ] **Tally XML/Excel Bridge:** Export sales, purchase, and payment vouchers formatted for Tally Prime import
- [ ] **Receivables Aging & Dunning Dashboard:** Automated 30/60/90 days client reminder escalation
- [ ] **Printable Barcode/QR Inventory Labels:** Sticker printing sheet for warehouse products and lots
- [ ] **Vendor Portal / RFQ Link:** Direct link for vendors to submit quotes against requirement inquiries

---

## Deployment History

| Date | Version | Changes |
|------|---------|---------|
| 2026-08-14 | Pre-Phase 7 | Last stable pre-hardening release |
| 2026-08-17 | Phase 7 | Security + performance fixes (17 issues resolved) |
| 2026-08-18 | Phase 8 | Live P&L, Order Kanban, WhatsApp Share, Morning Digest, FY Rollover, Google Drive Complete Backup |
