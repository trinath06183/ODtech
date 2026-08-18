# ODtech ERP — Suggested Improvements

## 🔴 Critical / Security

### 1. CSRF Middleware is Disabled
[`base.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/erp_project/settings/base.py#L50)
```python
# "django.middleware.csrf.CsrfViewMiddleware",   ← COMMENTED OUT
```
This exposes every state-changing POST endpoint to Cross-Site Request Forgery attacks. Re-enable it and ensure all forms include `{% csrf_token %}`. If some AJAX calls are failing, add the CSRF token via JS header instead of disabling middleware-wide protection.

---

### 2. Insecure Default `SECRET_KEY` in Base Settings
[`base.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/erp_project/settings/base.py#L6-L9)
```python
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-@gc&@e_gwg=2c3=...")
```
A hardcoded insecure fallback key is in `base.py`. If the env var is ever missing in production, Django silently uses this weak key. **Remove the default entirely** so Django raises an error instead:
```python
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]  # KeyError on missing → safe failure
```

---

### 3. `SECURE_HSTS_SECONDS` is Missing
[`base.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/erp_project/settings/base.py#L124)
`SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` are set, but `SECURE_HSTS_SECONDS` is **not set at all**. Without it, HSTS is effectively disabled. Add:
```python
SECURE_HSTS_SECONDS = 31536000  # 1 year
```

---

### 4. Debug Left-in Code in Production View
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L272-L277)
```python
data.append({
    'number': 'DEBUG',
    'customer': f"Count: {qs.count()} | since: {since} | metric: {metric}",
    ...
})
```
A debug row is being injected into the `orders_completed` drilldown API response. This leaks internal state info to clients and corrupts the UI. Remove it.

---

### 5. `dashboard_drilldown` View Has No `return` Statement
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L214-L313)
The function builds `data` but never returns a `JsonResponse`. Any call to this endpoint returns `None`, causing a Django `ValueError`. Add:
```python
    return JsonResponse({'metric': metric, 'period': period, 'data': data})
```
at the end of the function.

---

## 🟠 Performance

### 6. N+1 Query in Top Customers Loop
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L479-L480)
```python
for r in top_customers_qs:          # 10 iterations
    inv_nums = list(inv_qs.filter(..., contact_id=cid).values_list(...))
    paid_for_cust = float(Payment.objects.filter(document_ref__in=inv_nums).aggregate(...)['t'] or 0)
```
This fires **2 extra queries per customer** = up to 20 extra DB hits per API call. Batch-aggregate all payments per customer in a single query before the loop.

---

### 7. `sales_tracking_api` Monthly Mode Fires 6–7 DB Queries Per Month × 12
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L644-L649)
Each month row runs individual `Document` and `Order` queries. Consider using `annotate(month=TruncMonth(...))` to pull all months in 2–3 aggregated queries rather than 70+ individual ones.

---

### 8. `_legacy_kpis` Still Queries Invoices Twice
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L81-L83)
Even though `precomputed_sales_fy` is passed in, `total_invoiced` is separately calculated (all-time, not FY) which is a correct distinction — but the logic comment is misleading. Consider renaming for clarity.

---

### 9. Missing DB Index on `SystemActivityLog.path`
[`core/models.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/models.py#L16)
The `SystemActivityLog` list view supports text search on `path` and `user__username`. The `path` column is a `TextField` with no index. For large tables this becomes a full-table scan. Add `db_index=True` or use a `GinIndex` on PostgreSQL.

---

## 🟡 Code Quality

### 10. Bare `except Exception` Swallows Real Errors
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L163-L167) and [`L149`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L149)
```python
except Exception:
    pass
```
Silent failures on the EDMS block and legacy KPI block mean real bugs (e.g. missing FK, bad migration) go unnoticed. At minimum log them:
```python
except Exception:
    logger.exception("EDMS stats failed")
```

---

### 11. `Sum` Imported Twice in `dashboard()`
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L2) and [`L113`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L113)
`Sum` is imported at the top of the file and also re-imported as `DbSum` inside the view function. Just use the top-level import consistently.

---

### 12. Lazy Imports of Models Inside View Functions
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L24-L25) (pattern repeated in multiple views)
```python
def _sales_kpis(month_start, fy_start):
    from documents.models import Document
```
These per-call imports were likely added to dodge circular import issues. The better fix is to restructure your model imports (Django's app registry is fully loaded at view-call time). Lazy imports inside functions are a minor inefficiency (the module cache makes them cheap) but it's worth cleaning up.

---

### 13. Role Checks Use `getattr` String Comparison Instead of a Property
[`core/views.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/views.py#L674), [`core/decorators.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/core/decorators.py#L31)
```python
if not getattr(request.user, 'role', '') == 'Admin':
```
You already have `role_required` and `require_permission` decorators — use them consistently. The inline string comparison bypasses the permission abstraction and is a maintenance risk if role names change.

---

## 🟢 Architecture / Maintainability

### 14. `core/views.py` is 735 Lines — Should Be Split
The file mixes dashboard views, drilldown APIs, sales dashboard APIs, sales tracking APIs, and admin log views. Consider splitting into:
- `core/views/dashboard.py`
- `core/views/sales.py`
- `core/views/admin_logs.py`

---

### 15. `tracker/views.py` is 127 KB — Very Large
At 127 KB this is almost certainly doing too much. Break it down by feature into sub-modules or a `views/` package to improve navigability and reduce merge conflicts.

---

### 16. Missing `SECURE_HSTS_SECONDS` in Production and `SESSION_COOKIE_HTTPONLY` Not Explicitly Set
[`production.py`](file:///d:/ODtech/Main_work/Deployment/ODtech/erp_project/settings/production.py)
Add `SESSION_COOKIE_HTTPONLY = True` and `CSRF_COOKIE_HTTPONLY = True` explicitly (Django defaults these to `True`, but being explicit is a best practice for security audits).

---

### 17. No `requirements.txt` Pinning — Use Exact Versions
[`requirements.txt`](file:///d:/ODtech/Main_work/Deployment/ODtech/requirements.txt)
All dependencies use `>=` version ranges. For a production deployment this risks a `pip install` pulling a breaking update. Pin with `==` or generate a `requirements.lock` with `pip freeze`.

---

## Summary Table

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | 🔴 Critical | Security | CSRF middleware disabled |
| 2 | 🔴 Critical | Security | Insecure fallback SECRET_KEY |
| 3 | 🔴 Critical | Security | HSTS seconds missing |
| 4 | 🔴 Critical | Debug | Debug row in production API response |
| 5 | 🔴 Critical | Bug | `dashboard_drilldown` never returns a response |
| 6 | 🟠 High | Performance | N+1 queries in top-customers loop |
| 7 | 🟠 High | Performance | 70+ queries in monthly tracking API |
| 8 | 🟡 Medium | Performance | Misleading comment in `_legacy_kpis` |
| 9 | 🟡 Medium | Performance | No DB index on `path` column |
| 10 | 🟡 Medium | Code Quality | Silent bare `except` blocks |
| 11 | 🟡 Medium | Code Quality | `Sum` imported twice |
| 12 | 🟡 Medium | Code Quality | Lazy model imports in functions |
| 13 | 🟡 Medium | Code Quality | Inline role string comparisons |
| 14 | 🟢 Low | Maintainability | `core/views.py` too large |
| 15 | 🟢 Low | Maintainability | `tracker/views.py` too large |
| 16 | 🟢 Low | Security | Implicit cookie security settings |
| 17 | 🟢 Low | DevOps | Unpinned dependency versions |
