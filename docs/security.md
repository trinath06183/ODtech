# ODtech ERP — Security

> **Last Updated:** 2026-08-17

---

## 1. Authentication

| Control | Implementation |
|---------|---------------|
| **Login** | Custom `AbstractUser` (`users.User`); standard Django auth backend |
| **Brute-force protection** | `django-axes`: 3 failed attempts → 24-hour lockout |
| **Password reset** | 6-digit OTP sent via email; expires in 10 minutes (`OTP_EXPIRY_MINUTES`); single-use |
| **Session timeout** | 60 minutes of inactivity (`SESSION_COOKIE_AGE = 3600`, `SESSION_SAVE_EVERY_REQUEST = True`) |
| **Session cookie** | Named `odtech_bom_sessionid`; `HttpOnly=True`; `Secure=True` in production |
| **CSRF cookie** | Named `odtech_bom_csrftoken`; `HttpOnly=False` (allows frontend JS/AJAX to read token); `Secure=True` in production |

---

## 2. Authorization

### Role-based access
Every view is protected by at least one of:
- `@login_required` — basic authentication check
- `@role_required('Admin', ...)` — role-level check
- `@require_permission('SECTION', 'read'/'write')` — section-level granular check

### Section permissions
`UserSectionPermission` table grants `can_read` and `can_write` per user per app section.
**Admin** and **Managing Director** roles bypass all section checks.

### Field visibility
`UserFieldVisibility` lets admins restrict whether individual users can see:
- Selling price
- Purchase price
- Profit/loss
- Lot totals
- Internal notes

### EDMS document access
Documents have access levels: `owner` / `team` / `department` / `company-wide`.
Sensitive documents require OTP re-authentication.

---

## 3. Transport Security

| Setting | Value |
|---------|-------|
| `SECURE_SSL_REDIRECT` | `True` in production (env-configurable) |
| `SECURE_HSTS_SECONDS` | `31536000` (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` |
| `SECURE_HSTS_PRELOAD` | `True` |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` |
| `SECURE_BROWSER_XSS_FILTER` | `True` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |
| `SECURE_REFERRER_POLICY` | `same-origin` |
| `X_FRAME_OPTIONS` | `SAMEORIGIN` (allows preview iframe same-origin) |

---

## 4. CSRF Protection

CSRF middleware **must remain enabled** at all times (`django.middleware.csrf.CsrfViewMiddleware`).

- All HTML forms must include `{% csrf_token %}`
- AJAX POST requests must include the `X-CSRFToken` header:
  ```javascript
  // Read from cookie
  const csrfToken = document.cookie.split('; ')
    .find(r => r.startsWith('odtech_bom_csrftoken='))
    ?.split('=')[1];

  fetch('/api/endpoint/', {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  ```

> ⚠️ **Never comment out `CsrfViewMiddleware`.** This was identified as a critical vulnerability and fixed on 2026-08-17.

---

## 5. Audit Logging

### `SystemActivityLog` (core)
- Captures every **POST, PUT, DELETE, PATCH** request automatically via `ActivityTrackingMiddleware`
- Stores: `user`, `method`, `path`, `ip_address`, `payload` (passwords scrubbed, CSRF tokens excluded)
- Indexed on `timestamp` and `path` (index added 2026-08-17 via migration `0004_add_path_index_to_activity_log`)
- Access restricted to `Admin` role with mandatory password re-authentication and 15-minute session

### `AuditLog` (tracker)
- Captures every CREATE, UPDATE, DELETE, COMMENT on tracker models
- Stores: `user`, `action`, `model_name`, `object_id`, `object_repr`, `changes` (JSON)

### `ErrorLog` (tracker)
- Catches unhandled 500 errors via `ErrorLoggingMiddleware`
- Stores: `status_code`, `error_type`, `stack_trace`, `url`, `user`, `ip_address`
- Each error has a unique `reference_id` (UUID) for support tracing

---

## 6. File Upload Security

### EDMS files
- Stored in `edms_storage/` (configured via `EDMS_STORAGE_ROOT`) — **completely outside the web-served directory**
- Django serves files through a view with access control — never directly via URL
- Allowed extensions enforced: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, etc.
- MIME type validation on upload
- Max file size: `EDMS_MAX_UPLOAD_MB` (default 50 MB)

### Media files (tracker attachments, expense receipts)
- `validate_safe_file` validator applied on `FileField` uploads
- Image compression applied automatically on save for tracker product photos

---

## 7. Secret Management

| Secret | Where stored |
|--------|-------------|
| `DJANGO_SECRET_KEY` | Environment variable (required in production; no fallback) |
| `POSTGRES_PASSWORD` | Environment variable |
| `EMAIL_HOST_PASSWORD` | Environment variable |
| `EDMS_NOTIFY_EMAILS` | Environment variable |

> ⚠️ **Never commit `.env` files.** `.gitignore` excludes `.env` and `.venv`.

---

## 8. IP Address Handling

`ActivityTrackingMiddleware` correctly handles proxy headers:
```python
x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')
```
`SECURE_PROXY_SSL_HEADER` is set in production for proper HTTPS detection behind a reverse proxy.

---

## 9. Password Policy

Django's built-in validators are active:
- `UserAttributeSimilarityValidator`
- `MinimumLengthValidator`
- `CommonPasswordValidator`
- `NumericPasswordValidator`

---

## 10. Deployment Security Checklist

Run before every production deployment:

- [ ] `DJANGO_SECRET_KEY` env var is set and rotated from the old value
- [ ] `DEBUG=False` in production settings
- [ ] `ALLOWED_HOSTS` is explicitly set (no wildcards)
- [ ] `CSRF_TRUSTED_ORIGINS` lists only actual domain origins
- [ ] HTTPS enforced (`SECURE_SSL_REDIRECT=True`)
- [ ] DB password not hardcoded anywhere
- [ ] `edms_storage/` is outside the web root
- [ ] `staticfiles/` and `media/` are not writable by the application user
- [ ] `odtech.service` runs as a non-root user
- [ ] `django-axes` is active and limits are reasonable
- [ ] OTP expiry is ≤ 10 minutes
- [ ] System log access requires password re-authentication

---

## 11. Known Past Vulnerabilities (Fixed)

| Date | Issue | Fix |
|------|-------|-----|
| 2026-08-17 | CSRF middleware disabled (commented out) | Re-enabled `CsrfViewMiddleware` |
| 2026-08-17 | Insecure `SECRET_KEY` hardcoded as fallback | Removed fallback; env var required |
| 2026-08-17 | `SECURE_HSTS_SECONDS` missing → HSTS inactive | Added `SECURE_HSTS_SECONDS = 31536000` |
| 2026-08-17 | `SESSION_COOKIE_HTTPONLY` not explicit | Added explicit `True` in production settings |
| 2026-08-17 | Error details exposed in API response | Replaced with `logger.exception` + clean error JSON |
| 2026-08-17 | Debug row injected in `orders_completed` API | Removed debug data leak |
