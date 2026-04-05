# Admin Analytics Dashboard — Implementation Plan

## Overview

Build a dedicated admin analytics dashboard that gives `Admin` account users visibility into overall API usage trends across all users, with the ability to filter by organization, organization type, or sector, and export aggregated data to CSV.

**Key decisions:**
- Filters are separate views (not combined)
- CSV exports aggregated summary data (not raw logs)
- Separate page route (`/admin/analytics`), not an extension of the personal dashboard
- Filtering by organization includes per-user breakdown within that org
- Admin users get this new view instead of the personal usage dashboard

---

## Phase 1 — Backend Foundation

### Task 1: Admin authorization dependency

**File:** `app/deps.py`

- Add `get_current_admin()` — validates `account_type == "Admin"`, raises `AuthorizationError` if not
- Add `CurrentAdminDep = Annotated[User, Depends(get_current_admin)]` type alias

### Task 2: Admin CRUD queries

**File (new):** `app/crud/admin_monitoring.py`

| Function | Purpose |
|----------|---------|
| `get_all_logs_since(db, since)` | All logs within time range |
| `get_logs_by_organization(db, organization, since)` | Filter by org (includes per-user data) |
| `get_logs_by_organization_type(db, org_type, since)` | Filter by org type |
| `get_logs_by_sector(db, sector, since)` | Filter by sector |
| `get_usage_stats_all(db)` | All-time aggregated endpoint counts (no user filter) |
| `get_unique_organizations(db)` | Distinct orgs for filter dropdowns |
| `get_unique_organization_types(db)` | Distinct org types |
| `get_unique_sectors(db)` | Distinct sectors |

### Task 3: Admin aggregation utils

**File (new):** `app/utils/admin_monitoring_utils.py`

- `get_admin_dashboard_stats(db, time_range, filter_type=None, filter_value=None)`
- Reuses `_bucket_format` and `_generate_labels` from existing `monitoring_utils.py`
- Four view modes: overview (all data), organization, organization_type, sector
- Per-user breakdown when filtering by organization
- Returns same chart structure as existing dashboard (volume, latency, distribution) but across all users

### Task 4: Admin analytics router

**File (new):** `app/routers/admin_analytics.py`

| Endpoint | Purpose |
|----------|---------|
| `GET /api/admin/analytics/overview?time_range=7d` | Overall trends across all users |
| `GET /api/admin/analytics/by-organization?organization=X&time_range=7d` | Org view with per-user breakdown |
| `GET /api/admin/analytics/by-organization-type?organization_type=NGO&time_range=7d` | Org type view |
| `GET /api/admin/analytics/by-sector?sector=Health&time_range=7d` | Sector view |
| `GET /api/admin/analytics/filters` | Available orgs, org types, sectors for dropdowns |
| `GET /api/admin/analytics/export?view=overview&time_range=7d` | CSV export |

Register router in `app/api.py`.

### Task 5: CSV export utility

- Convert aggregated stats dict to CSV format
- Return `StreamingResponse` with `text/csv` content type
- Includes: endpoint, request count, avg latency, and (when filtered by org) per-user counts

---

## Phase 2 — Frontend

### Task 6: Admin analytics data hook

**File (new):** `frontend/src/hooks/useAdminAnalytics.ts`

- Fetches from `/api/admin/analytics/*` endpoints
- Manages filter state (view type, filter value, time range)

### Task 7: Admin filter components

**File (new):** `frontend/src/components/admin/FilterBar.tsx`

- View selector: Overview / By Organization / By Org Type / By Sector
- Dropdown for the selected filter's values (populated from `/api/admin/analytics/filters`)
- Time range selector (reuse existing options)

### Task 8: Admin analytics page

**File (new):** `frontend/src/pages/AdminAnalytics.tsx`

- Route: `/admin/analytics`
- Metric cards: total requests, total users, avg latency, most active org
- Charts: request volume over time, latency trends, endpoint distribution
- When filtered by org: per-user breakdown table
- Export CSV button

### Task 9: Routing and navigation

- Add `/admin/analytics` route in `frontend/src/App.tsx` (protected, admin only)
- Redirect admin users from `/dashboard` to `/admin/analytics`
- Add nav link in header/sidebar for admin users

---

## Phase 3 — Tests

### Task 10: Backend endpoint tests

**File (new):** `app/tests/test_admin_analytics.py`

- Admin authorization (non-admin gets 403, admin gets 200)
- Overview stats with test log data
- Filter by organization with per-user breakdown
- Filter by organization type
- Filter by sector
- CSV export returns valid CSV content
- Filters endpoint returns correct options
- Invalid filter values return 400

### Task 11: Unit tests for admin aggregation utils

- Test aggregation across multiple users/orgs
- Test per-user breakdown grouping
- Test CSV generation

---

## File Change Summary

| Action | File |
|--------|------|
| Modify | `app/deps.py` — add `get_current_admin`, `CurrentAdminDep` |
| Create | `app/crud/admin_monitoring.py` — admin-level queries |
| Create | `app/utils/admin_monitoring_utils.py` — admin aggregation logic |
| Create | `app/routers/admin_analytics.py` — admin API endpoints |
| Modify | `app/api.py` — register admin router |
| Create | `frontend/src/hooks/useAdminAnalytics.ts` |
| Create | `frontend/src/components/admin/FilterBar.tsx` |
| Create | `frontend/src/pages/AdminAnalytics.tsx` |
| Modify | `frontend/src/App.tsx` — add route + admin redirect |
| Modify | `frontend/src/components/Header.tsx` (or Layout) — admin nav link |
| Create | `app/tests/test_admin_analytics.py` |

## Trade-offs

- **Separate views vs combined filters**: Simpler queries and UI now; combined filters can be added later.
- **Reusing chart helpers**: `_bucket_format`/`_generate_labels` shared with personal dashboard, avoiding duplication.
- **CSV as aggregated data**: Smaller files, faster exports. Raw log export can be added later if needed.
