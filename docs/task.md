# Fix Tasks

## Settings
- [x] Fix #1: Re-enable CSRF middleware in base.py
- [x] Fix #2: Remove insecure fallback SECRET_KEY from base.py
- [x] Fix #3: Add SECURE_HSTS_SECONDS to base.py
- [x] Fix #16: Add explicit SESSION/CSRF cookie security flags to production.py

## core/views.py
- [x] Fix #4: Remove debug row from orders_completed drilldown
- [x] Fix #5: Add missing return JsonResponse in dashboard_drilldown
- [x] Fix #6: Resolve N+1 in top-customers loop (batch payment aggregation)
- [x] Fix #7: Optimize monthly tracking API (bulk annotate)
- [x] Fix #10: Replace bare except with logger.exception
- [x] Fix #11: Remove duplicate Sum / DbSum import
- [x] Fix #13: Use role_required decorator in LogUnlockView / SystemActivityLogView

## core/models.py
- [x] Fix #9: Add db_index to SystemActivityLog.path

## requirements.txt
- [x] Fix #17: Pin exact dependency versions
