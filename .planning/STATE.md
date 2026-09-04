# GSD Project State

> **Last Updated:** 2026-09-04  
> **Status:** Codebase Mapped & Initialized  

---

## 1. Project Overview
- **Name:** ODtech ERP
- **Framework:** Django 4.2+ (Python) with PostgreSQL & WhiteNoise
- **Primary Modules:**
  - `tracker`: Manufacturing & Order tracker (Lots, Costs, Approvals)
  - `documents`: Commercial billing documents (Invoices, Quotations, Proformas)
  - `edms`: Enterprise Document Management System
  - `inventory`: Product stock transactions & warranties
  - `reporting`: Executive Company Overview Dashboard & P&L
  - `payments`: Accounts, cash flows, and payables/receivables
  - `users`: Custom authentication, roles, and section permissions

---

## 2. Codebase Map
All 7 foundational architectural documents have been generated in `.planning/codebase/`:
- [STACK.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/STACK.md)
- [INTEGRATIONS.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/INTEGRATIONS.md)
- [ARCHITECTURE.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/ARCHITECTURE.md)
- [STRUCTURE.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/STRUCTURE.md)
- [CONVENTIONS.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/CONVENTIONS.md)
- [TESTING.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/TESTING.md)
- [CONCERNS.md](file:///d:/ODtech/Main_work/Deployment/ODtech/.planning/codebase/CONCERNS.md)

---

## 3. Recent Work Completed
- Fixed Total Purchases KPI card and EDMS filter in `reporting/views.py` and `financial_dashboard.html` to target actual Invoices/Purchase Invoices and exclude Proforma Invoices (`PRO`).
- Added document list previous/next navigation with active filter preservation.
- Added Execution Planning Dashboard auto-import and cash gap warning banner.
- Installed and activated GSD Core.

---

## 4. Next Recommended Actions
- Deploy recent bug fixes to the production server.
- Plan next feature or optimization phase via `/gsd-plan-phase`.
