# ODtech ERP — Developer Guide

> **Last Updated:** 2026-08-17  
> The single reference for making changes quickly and correctly.

---

## Quick Reference: Where Is Everything?

| What you want to change | File |
|-------------------------|------|
| Dashboard KPIs (month/FY cards) | [`core/views.py`](core/views.py) → `_sales_kpis()`, `_orders_received_kpis()` etc. |
| Dashboard drilldown (slide panel) | [`core/views.py`](core/views.py) → `dashboard_drilldown()` |
| Sales Dashboard charts + API | [`core/views.py`](core/views.py) → `sales_dashboard_api()` |
| Sales Tracking table | [`core/views.py`](core/views.py) → `sales_tracking_api()` |
| Main dashboard HTML | [`templates/core/dashboard.html`](templates/core/dashboard.html) |
| Sales dashboard HTML | [`templates/core/sales_dashboard.html`](templates/core/sales_dashboard.html) |
| Sidebar / base layout | [`templates/base.html`](templates/base.html) |
| URL routes | [`erp_project/urls.py`](erp_project/urls.py) → app `urls.py` |
| User roles list | [`users/models.py`](users/models.py) → `User.ROLE_CHOICES` |
| App sections for permissions | [`users/models.py`](users/models.py) → `AppSection` |
| Company profile (logo, GST, bank) | [`config/models.py`](config/models.py) |
| Document types | [`documents/models.py`](documents/models.py) → `Document.DOCUMENT_TYPES` |
| GST logic (IGST vs CGST/SGST) | [`documents/services.py`](documents/services.py) → `TaxService` |
| Order statuses | [`tracker/models.py`](tracker/models.py) → `Order.STATUS_CHOICES` |
| Field visibility per user | [`tracker/models.py`](tracker/models.py) → `UserFieldVisibility` |
| CSRF / security middleware order | [`erp_project/settings/base.py`](erp_project/settings/base.py) → `MIDDLEWARE` |
| Production security settings | [`erp_project/settings/production.py`](erp_project/settings/production.py) |
| EDMS file storage path | [`erp_project/settings/base.py`](erp_project/settings/base.py) → `EDMS_STORAGE_ROOT` |
| Email SMTP config | [`erp_project/settings/base.py`](erp_project/settings/base.py) → `EMAIL_*` |
| Session timeout | [`erp_project/settings/base.py`](erp_project/settings/base.py) → `SESSION_COOKIE_AGE` |
| Brute-force lockout | [`erp_project/settings/base.py`](erp_project/settings/base.py) → `AXES_FAILURE_LIMIT` |
| Scheduled jobs | [`users/scheduler.py`](users/scheduler.py), [`edms/`](edms/) |
| Activity log access | System Logs → Admin password re-auth → `/system-logs/` |

---

## Local Development Setup

```bash
# 1. Clone repo
git clone https://github.com/trinath06183/ODtech.git
cd ODtech

# 2. Create virtualenv
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env (copy from this template)
# DJANGO_SETTINGS_MODULE=erp_project.settings.development
# POSTGRES_DB=odtech_db
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=yourpassword

# 5. Run migrations
python manage.py migrate --settings=erp_project.settings.development

# 6. Create superuser
python manage.py createsuperuser --settings=erp_project.settings.development

# 7. Run dev server
python manage.py runserver --settings=erp_project.settings.development
```

---

## Making a Code Change

### Standard workflow
```bash
# 1. Edit files locally (in d:\ODtech\Main_work\Deployment\ODtech\)
# 2. Test locally
# 3. Commit
git add <files>
git commit -m "type: short description"
git push origin main

# 4. On server (SSH in)
cd /home/server_admin/ODtech
source venv/bin/activate
git pull origin main
# If models changed:
python3 manage.py makemigrations --settings=erp_project.settings.production
python3 manage.py migrate --settings=erp_project.settings.production
# If static files changed:
python3 manage.py collectstatic --noinput --settings=erp_project.settings.production
# Always:
sudo systemctl restart odtech.service
sudo systemctl status odtech.service
```

### If git pull is blocked by local server changes
```bash
git fetch origin main
git reset --hard origin/main   # Discards all local server changes
```

---

## Adding a New Django App

```bash
python manage.py startapp myapp --settings=erp_project.settings.development
```

Then:
1. Add `'myapp'` to `INSTALLED_APPS` in `base.py`
2. Add URL include to `erp_project/urls.py`
3. Add the app section to `users/models.py → AppSection` if it needs permission control
4. Create models extending `TimeStampedModel`
5. Add `@login_required` + `@require_permission(...)` to all views

---

## Adding a New Dashboard KPI

1. Write a `_my_kpi(month_start, fy_start)` function in `core/views.py`
2. Call it in `dashboard()` alongside the other KPIs
3. Pass result to the template context dict
4. Add the card HTML to `templates/core/dashboard.html`

---

## Adding a New User Role

1. Add the role tuple to `User.ROLE_CHOICES` in `users/models.py`
2. Run `makemigrations users` + `migrate`
3. Add role handling in any `@role_required(...)` decorators that should include it
4. Update `User.has_section_perm()` if the new role needs auto-bypass behavior

---

## Running Migrations

```bash
# Local dev
python manage.py makemigrations --settings=erp_project.settings.development
python manage.py migrate --settings=erp_project.settings.development

# Production (on server)
python3 manage.py makemigrations --settings=erp_project.settings.production
python3 manage.py migrate --settings=erp_project.settings.production
```

---

## Checking Logs

```bash
# Live gunicorn logs
journalctl -u odtech.service -f

# Last 100 lines
journalctl -u odtech.service -n 100

# Django error logs (from ErrorLoggingMiddleware)
# Access via: Admin → System Logs in the app

# Activity log
# Access via: Admin → System Logs (requires password re-auth)
```

---

## Server SSH Access

```bash
ssh server_admin@192.168.1.106
# Password required

# Project location
cd /home/server_admin/ODtech

# Virtualenv
source venv/bin/activate

# Service commands
sudo systemctl restart odtech.service
sudo systemctl status odtech.service
sudo systemctl stop odtech.service
```

---

## Commit Message Convention

```
type: short description (max 72 chars)

Types:
  feat     — new feature
  fix      — bug fix
  security — security fix
  perf     — performance improvement
  refactor — code restructure without feature change
  docs     — documentation only
  style    — formatting, no logic change
  test     — adding/fixing tests
  deploy   — deployment/infrastructure change
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DJANGO_SETTINGS_MODULE` | Yes | — | `erp_project.settings.production` or `.development` |
| `DJANGO_SECRET_KEY` | Yes (prod) | dev placeholder | Django secret key |
| `DJANGO_ALLOWED_HOSTS` | Yes (prod) | — | Comma-separated allowed hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes (prod) | — | Comma-separated trusted origins |
| `POSTGRES_DB` | Yes | `odtech_db` | Database name |
| `POSTGRES_USER` | Yes | `postgres` | Database user |
| `POSTGRES_PASSWORD` | Yes | — | Database password |
| `POSTGRES_HOST` | No | `localhost` | Database host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP host |
| `EMAIL_HOST_USER` | No | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | No | — | SMTP password |
| `EDMS_MAX_UPLOAD_MB` | No | `50` | Max EDMS file size |
| `EDMS_NOTIFY_EMAILS` | No | — | Comma-separated security alert emails |
| `OTP_EXPIRY_MINUTES` | No | `10` | OTP validity window |
| `DJANGO_SECURE_SSL_REDIRECT` | No | `true` | Force HTTPS redirect |
| `DJANGO_TIME_ZONE` | No | `Asia/Kolkata` | Server timezone |

---

## Key Files to Know

| File | Why it matters |
|------|---------------|
| [`erp_project/settings/base.py`](erp_project/settings/base.py) | All shared config — MIDDLEWARE, INSTALLED_APPS, security headers |
| [`erp_project/settings/production.py`](erp_project/settings/production.py) | Production DB, HTTPS, cookie security |
| [`core/views.py`](core/views.py) | Dashboard, sales dashboard, drilldown, activity log views |
| [`core/middleware.py`](core/middleware.py) | POST/PUT/DELETE audit logging |
| [`core/decorators.py`](core/decorators.py) | `login_required`, `role_required`, `require_permission` |
| [`users/models.py`](users/models.py) | User roles, section permissions, OTP |
| [`tracker/models.py`](tracker/models.py) | Full order tracking data model |
| [`documents/models.py`](documents/models.py) | Commercial documents, GST, multi-currency |
| [`documents/services.py`](documents/services.py) | Tax service, document number generation |
