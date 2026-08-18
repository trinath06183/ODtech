# ODtech ERP — Architecture

> **Last Updated:** 2026-08-17

---

## 1. High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                         │
│               HTML + Vanilla JS + CSS (WhiteNoise)              │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS (nginx / ngrok)
┌────────────────────────────▼────────────────────────────────────┐
│                  gunicorn (odtech.service)                       │
│         3 workers · /home/server_admin/ODtech/venv              │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   Django 4.2+ Application                       │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  core    │ │  users   │ │ tracker  │ │    documents     │   │
│  │dashboard │ │auth/roles│ │orders   │ │QTN/INV/PO/etc.  │   │
│  │activity  │ │perms/OTP │ │products │ │multi-currency   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │inventory │ │contacts  │ │payments  │ │      edms        │   │
│  │stock/    │ │clients & │ │payments/ │ │private file     │   │
│  │warranty  │ │vendors   │ │expenses  │ │management       │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │reporting │ │  config  │ │ mobile_  │                        │
│  │reports   │ │company   │ │ upload   │                        │
│  │          │ │profile   │ │QR upload │                        │
│  └──────────┘ └──────────┘ └──────────┘                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│              PostgreSQL (localhost:5432)                         │
│              Database: odtech_db                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Django App Structure

```
ODtech/
├── erp_project/              # Project config
│   ├── settings/
│   │   ├── base.py           # Shared settings (all environments)
│   │   ├── development.py    # Local dev overrides
│   │   ├── production.py     # Production overrides (env vars required)
│   │   └── sqlite.py         # Lightweight SQLite mode
│   ├── urls.py               # Root URL dispatcher
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                     # Shared foundations
│   ├── models.py             # TimeStampedModel, SystemActivityLog, DocumentLink
│   ├── views.py              # Dashboard, Sales Dashboard, Activity Log views
│   ├── middleware.py         # ActivityTrackingMiddleware
│   ├── decorators.py         # login_required, role_required, require_permission
│   ├── utils.py              # money() helper
│   └── validators.py
│
├── users/                    # Authentication & authorization
│   ├── models.py             # User (AbstractUser), UserSectionPermission, OTPToken
│   ├── middleware.py         # OnboardingMiddleware
│   └── scheduler.py         # OTP cleanup job
│
├── tracker/                  # Order management (largest app)
│   ├── models.py             # Order, Lot, Product, SupplierCostOption,
│   │                         # PriceApprovalRequest, Task, Notification,
│   │                         # InternalNote, AuditLog, ErrorLog,
│   │                         # UserFieldVisibility, UserNote, UserTodo
│   ├── middleware.py         # CurrentUserMiddleware, ErrorLoggingMiddleware
│   ├── signals.py            # Post-save signals for audit logs
│   └── views.py              # 127KB — full CRUD + AJAX APIs
│
├── documents/                # Commercial documents
│   ├── models.py             # Document, DocumentItem
│   ├── services.py           # TaxService, document number generation
│   ├── signals.py            # Auto-update document totals
│   └── views.py
│
├── inventory/                # Stock & warranty
│   ├── models.py             # Product, StockTransaction,
│   │                         # WarrantyRegistration, WarrantyClaim
│   └── services.py          # StockService
│
├── contacts/                 # Client/vendor directory
├── payments/                 # Payments & expense claims
├── edms/                     # Enterprise Document Management
│   ├── models.py             # EDMSDocument, EDMSCategory, EDMSAccessLog
│   └── services/             # File storage, OTP, email services
│
├── reporting/                # Reports
├── config/                   # Company profile
├── mobile_upload/            # QR-code upload
│
├── templates/                # All HTML templates (Django template engine)
├── static/                   # CSS, JS, images (WhiteNoise served)
├── staticfiles/              # collectstatic output
├── edms_storage/             # Private file storage (NOT served via HTTP)
└── media/                    # Public media (product docs, attachments)
```

---

## 3. Data Model Relationships

```
User ──────────────────────────────────────────────────────────┐
 │ role, section_permissions                                    │
 │                                                              │
Contact ────────────────────────────────────────────┐          │
 │                                                  │          │
 ├── Document (QTN/INV/PO/etc.) ──── DocumentItem ──┼── Product (inventory)
 │    └── DocumentLink (many-to-many across types)  │
 │                                                  │
 ├── Payment                                        │
 │                                                  │
 └── (tracker) Order ──── Lot ──── Product (tracker)┘
                           │        │
                           │        ├── SupplierCostOption
                           │        ├── PriceApprovalRequest
                           │        ├── Task
                           │        ├── InternalNote
                           │        ├── AuditLog
                           │        └── ProductExpense
                           │
                           └── OrderExpense

EDMSDocument ── EDMSCategory
             └── EDMSAccessLog

SystemActivityLog ── User
AuditLog ── User
ErrorLog ── User
```

---

## 4. Middleware Stack (in order)

```
1. SecurityMiddleware          — HTTPS, XSS, content-type headers
2. WhiteNoiseMiddleware        — Static file serving
3. SessionMiddleware           — Session handling
4. CommonMiddleware            — URL normalization
5. CsrfViewMiddleware          — CSRF protection (RE-ENABLED 2026-08-17)
6. AuthenticationMiddleware    — Attaches request.user
7. MessageMiddleware           — Flash messages
8. XFrameOptionsMiddleware     — Clickjacking protection (SAMEORIGIN)
9. OnboardingMiddleware        — Redirects unboarded users
10. CurrentUserMiddleware      — Thread-local user storage for signals
11. ErrorLoggingMiddleware     — Catches 500s → ErrorLog
12. ActivityTrackingMiddleware — POST/PUT/DELETE → SystemActivityLog
13. AxesMiddleware             — Brute-force lockout
```

---

## 5. Request Lifecycle

```
Browser Request
      │
      ▼
[Middleware chain] (top-down, numbered above)
      │
      ▼
[URL Router] erp_project/urls.py → app urls.py
      │
      ▼
[Decorator checks] login_required / role_required / require_permission
      │
      ▼
[View function / class]
      │
      ├── DB queries (via Django ORM → psycopg2 → PostgreSQL)
      ├── Template rendering (Django template engine)
      └── JsonResponse (for AJAX API endpoints)
      │
      ▼
[Response] → WhiteNoise (static) or gunicorn (dynamic)
```

---

## 6. Deployment Architecture

```
Ubuntu 26.04 Server (192.168.1.106)
│
├── /home/server_admin/ODtech/          ← Project root
│   ├── venv/                           ← Python 3.14 virtualenv
│   ├── erp_project/settings/production.py
│   ├── staticfiles/                    ← collectstatic output
│   ├── edms_storage/                   ← Private EDMS files
│   └── media/                          ← Public uploads
│
├── /etc/systemd/system/odtech.service  ← gunicorn service
│   └── 3 workers, binds to 0.0.0.0:8000
│
└── PostgreSQL (localhost:5432)
    └── odtech_db
```

**Service management:**
```bash
sudo systemctl restart odtech.service   # Restart
sudo systemctl status odtech.service    # Check health
journalctl -u odtech.service -f         # Live logs
```

---

## 7. Settings Architecture

| File | Purpose |
|------|---------|
| `base.py` | All shared settings; `SECRET_KEY` read from env var only |
| `development.py` | `DEBUG=True`; local PostgreSQL; all hosts allowed; CSRF for ngrok |
| `production.py` | `DEBUG=False`; env-var DB; HTTPS redirect; secure cookies; HSTS |
| `sqlite.py` | Lightweight SQLite for quick local testing |

**Active settings selected via `DJANGO_SETTINGS_MODULE` env var.**

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Custom `login_required` decorator | Needed `?next=` redirect with URL-encoded full path |
| Lazy model imports inside helper functions | Avoids circular imports between `core`, `documents`, `tracker` |
| `DocumentLink` generic FK table | Allows any document type to be linked to any other without changing models |
| Stock calculated by SUM of `StockTransaction` | Ledger-style audit trail; no denormalized "current stock" field to go stale |
| Payments linked via `document_ref` string | Payments can reference any document number across the document lifecycle graph |
| `edms_storage/` outside `media/` | Private files must never be served directly by WhiteNoise |
| `TimeStampedModel` abstract base | All key models inherit `created_at` / `updated_at` automatically |
| `UserFieldVisibility` model | Allows admin to restrict what financial columns each user sees in tracker |
