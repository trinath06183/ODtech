# ODtech ERP — Product Requirements Document (PRD)

> **Last Updated:** 2026-08-17 | **Version:** 1.0 | **Status:** Live / Production

---

## 1. Product Overview

ODtech ERP is a full-stack, web-based Enterprise Resource Planning system built for **ODtech** — a manufacturing, trading, and engineering services company based in Odisha, India. It replaces fragmented spreadsheets and siloed tools with a single, role-secured platform covering the full order-to-cash and procure-to-pay lifecycle.

### Goals
- Unify order management, commercial documents, payments, inventory, and internal file management
- Give management real-time financial and operational visibility via dashboards
- Enforce role-based access so sensitive financial data is only visible to authorized users
- Run as a self-hosted solution on a local Ubuntu server within the company network

---

## 2. Users & Roles

| Role | Description |
|------|-------------|
| **Managing Director** | Full access; bypasses all permission checks |
| **Director** | Full access; same as MD for system purposes |
| **Admin** | Manages users, system logs, configurations |
| **Purchase** | Manages procurement, supplier tracking, purchase orders |
| **Accounts** | Manages invoices, payments, financial reports |
| **Tender** | Manages quotations and proposal documents |
| **HR** | Employee-related access |
| **Engineering** | Product/technical order tracking |
| **Project** | Project tracking and order management |
| **Viewer** | Read-only access to permitted sections |
| **Staff** | Default minimal access role |

Each role's access is further controlled via `UserSectionPermission` (read/write per App Section).

**App Sections:** DASHBOARD, USERS, CONTACTS, INVENTORY, EDMS, PAYMENTS, REPORTING, TRACKER, DOCUMENTS

---

## 3. Core Modules

### 3.1 Order Tracker (`tracker`)
Tracks every customer order from receipt through sourcing, procurement, shipping, and closure.

**Key entities:**
- `Order` — top-level work unit; statuses: OPEN → SOURCING → PROCURED → SHIPPED → CLOSED; payment statuses: UNPAID → PARTIALLY_PAID → PAID
- `Lot` — optional grouping of products within an order
- `Product` (tracker) — line item with dual customer + supplier stage tracking
- `SupplierCostOption` — multiple supplier quotes per product with one selected
- `PriceApprovalRequest` — approval workflow for prices below minimum margin
- `Task` — assignable tasks linked to orders/products (Priority: LOW/MEDIUM/HIGH/CRITICAL)
- `InternalNote` — private team notes
- `AuditLog` — immutable change history per action

**Customer stages:** Requirement Received → Quotation Given → PO Received → PI Given → Product Given → Invoice Given
**Supplier stages:** Requirement Searching → Quotation Received → PO Given → PI Received → Product Received → Invoice Received

### 3.2 Commercial Documents (`documents`)
Generate, manage, and track all outward commercial documents.

**Document types:** QTN (Quotation), PRO (Proforma Invoice), INV (Invoice), CHL (Delivery Challan), PO (Purchase Order), CRN (Credit Note), DBN (Debit Note)

**Key features:**
- Multi-currency: INR, USD, EUR, GBP, AED, SAR, CAD, AUD, SGD, JPY
- GST: CGST+SGST or IGST, auto-detected from contact state; overridable per document
- Discount modes: none / global fixed / global % / individual ₹ / individual %
- Amount-in-words (Indian numbering for INR)
- Document lifecycle linking: QTN → PRO → INV → CHL via `DocumentLink`
- Payment milestones, transporter/e-way bill fields for Delivery Challans

### 3.3 Payments (`payments`)
- `Payment` — incoming payments linked to contact + document reference; modes: Cash, Bank Transfer, Cheque, Credit Card, UPI
- `Expense` — employee claims: Pending → Approved → Rejected → Paid; Daily vs Fixed Cost categories

### 3.4 Inventory (`inventory`)
- `Product` — catalogue item with SKU, HSN code, tax rate, selling/purchase price, reorder level
- `StockTransaction` — ledger entries (IN/OUT/ADJUSTMENT) for real-time stock via aggregation
- `WarrantyRegistration` — customer warranty records linked to invoice
- `WarrantyClaim` — claim processing: Pending → In Review → Resolved/Rejected

### 3.5 Contacts (`contacts`)
Central directory of all clients and vendors. Stores GST number, state code (IGST determination), billing/shipping address. Used across documents, payments, and tracker.

### 3.6 EDMS (`edms`)
Private internal document repository.
- Files stored in `edms_storage/` (outside `media/`) — never served directly
- Category-based organization with owner and access-level controls (owner / team / department / company)
- OTP-based access for sensitive documents; email notifications for activity
- Soft-delete; configurable max upload size (default 50 MB)

### 3.7 Reporting (`reporting`)
Financial and operational report generation for management.

### 3.8 Config (`config`)
Company profile: logo, address, GST number, bank details, terms toggle, document numbering prefix.

### 3.9 Mobile Upload (`mobile_upload`)
QR-code based mobile document upload for field staff without desktop access.

### 3.10 Dashboards (`core`)
- **Main Dashboard** — KPI cards (Sales, Orders, Documents) for current month + FY; inventory overview; personal todos/notes; EDMS activity
- **Sales Dashboard** — Revenue chart (30 days), top-10 customers, order/payment status breakdown, activity feed; AJAX-powered with period filter
- **Sales Tracking** — Month-by-month and year-by-year breakdown of quotations, orders, invoices, and payments

---

## 4. Non-Functional Requirements

| Requirement | Detail |
|-------------|--------|
| Authentication | Custom `AbstractUser`; django-axes brute-force lockout (3 attempts, 24h cooldown) |
| Session | 60-minute inactivity timeout (`SESSION_COOKIE_AGE = 3600`) |
| Audit | POST/PUT/DELETE → `SystemActivityLog`; tracker actions → `AuditLog` |
| Security | CSRF enabled, HSTS 1 year, XSS/content-type headers, secure + httponly cookies |
| Performance | `select_related`/`prefetch_related` on list views; aggregated dashboard queries via `annotate` |
| Deployment | Ubuntu 26.04, gunicorn + systemd (`odtech.service`), PostgreSQL, WhiteNoise static |
| PWA | `manifest.json` + `service-worker.js` for mobile installability |
| Scheduling | `django-apscheduler` for background jobs |
| Compression | `django-compressor` minifies CSS/JS in production |

---

## 5. Indian Financial Year
All FY KPIs use **April 1 → March 31**.

---

## 6. Out of Scope (Current Version)
- Multi-company / multi-branch support
- E-invoice / IRN (GST portal integration)
- Automatic bank reconciliation
- Native mobile app (PWA serves this need)
- Public customer portal
