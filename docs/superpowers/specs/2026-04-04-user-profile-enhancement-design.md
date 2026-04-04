# User Profile Enhancement — Design Spec

**Date:** 2026-04-04
**Status:** Draft
**Approach:** Incremental Extension (add columns to existing User model)

## Objective

Centralize user identity data (full name, organization type, impact sectors) to enable sector-based reporting on the analytics dashboard. Existing users must not be broken — new fields are nullable, and a persistent banner guides them to complete their profiles.

## Scope

- Add profile fields to backend User model and registration flow
- Build profile update endpoint (`PUT /auth/profile`) and profile status endpoint (`GET /auth/profile/status`)
- Extend frontend registration form with new fields
- Build a `/complete-profile` page for Google OAuth users and existing users
- Add a persistent dashboard banner for users with incomplete profiles
- Update Account Settings page with new editable profile fields
- Denormalize `organization_type` and `sector` into `EndpointLog` for future reporting

**Out of scope:** Sector-based reporting/analytics dashboard, admin views, multi-tenant filtering.

## Data Model

### User Model — New Columns

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `full_name` | `String` | Yes | `None` | Display name |
| `organization_type` | `String` | Yes | `None` | One of: `NGO`, `Government`, `Private Sector`, `Research`, `Individual`, `Other` |
| `sector` | `JSON` | Yes | `None` | Array of strings, e.g. `["Health", "Education"]`. JSON for SQLite test compat |

### EndpointLog Model — New Columns

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| `organization_type` | `String` | Yes | `None` |
| `sector` | `JSON` | Yes | `None` |

Populated from the authenticated user's profile during request logging in `MonitoringMiddleware`.

### Profile Completeness

A profile is "complete" when all of the following are non-null/non-empty:
- `full_name`
- `organization` (not `"Unknown"`)
- `organization_type`
- `sector` (non-empty list)

This is a computed check (property or utility function), not a stored column.

### Migration

Single Alembic migration adding all new columns to both `users` and `endpoint_logs` tables. All columns nullable so existing rows are unaffected.

## Pydantic Schema Changes

### New Schemas

**`ProfileUpdate`** — request body for `PUT /auth/profile`:
```python
class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    organization: Optional[str] = None
    organization_type: Optional[str] = None  # validated against allowed list
    sector: Optional[List[str]] = None
```

**`ProfileCompletionStatus`** — response for `GET /auth/profile/status`:
```python
class ProfileCompletionStatus(BaseModel):
    is_complete: bool
    missing_fields: List[str]
```

### Modified Schemas

- **`User`** (response) — add `full_name`, `organization_type`, `sector` fields
- **`UserCreate`** — add `full_name` (optional), `organization_type` (optional), `sector` (optional). Optional at the API level to avoid breaking existing API consumers; the frontend form enforces them as required via client-side validation.
- **`UserGoogle`** — no change (new fields come from profile completion page)

## Allowed Values

### Organization Types (fixed list + Other)
- `NGO`
- `Government`
- `Private Sector`
- `Research`
- `Individual`
- `Other`

### Impact Sectors (preset + custom)
Preset values:
- `Health`
- `Agriculture`
- `Energy`
- `Environment`
- `Education`
- `Governance`

Users can also add custom sector strings. Backend accepts any non-empty string in the sector list.

## Backend API Changes

### New Endpoints

**`PUT /auth/profile`**
- Auth: Required (`CurrentUserDep`)
- Body: `ProfileUpdate` (all fields optional — partial updates)
- Validates `organization_type` against allowed list if provided
- Validates `sector` is a list of non-empty strings if provided
- Returns updated `User` schema
- New CRUD function: `update_user_profile(db, user_id, profile_data)`

**`GET /auth/profile/status`**
- Auth: Required (`CurrentUserDep`)
- Returns `ProfileCompletionStatus`
- No writes, lightweight check

### Modified Endpoints

**`POST /auth/register`**
- Add to request body: `full_name` (optional), `organization_type` (optional), `sector` (optional)
- All new fields optional at the API level to preserve backward compatibility for existing API consumers
- Frontend registration form enforces `organization_type` and `sector` as required via client-side validation
- New users via the web form will have complete profiles from registration

**`GET /auth/google/callback`**
- Change redirect from `/setup-organization` to `/complete-profile` when profile is incomplete
- Existing Google users logging in with incomplete profiles also redirect to `/complete-profile`

### Modified Middleware

**`MonitoringMiddleware`** (`app/middleware.py`)
- When logging to `EndpointLog`, look up the authenticated user's `organization_type` and `sector`
- Write them to the new log columns
- Falls back to `None` if user isn't authenticated or fields are missing

### Deprecated

**`/setup-organization`** — replaced by `/complete-profile` + `PUT /auth/profile`. Keep backend endpoint working for backward compat but frontend no longer links to it.

## Frontend Changes

### Updated: Registration Form (`/register`)

Add three new fields to the existing form, between Organization and Password:
1. **Full Name** — text input, optional, with User icon
2. **Organization Type** — dropdown select with preset options + "Other"
3. **Impact Sectors** — chip/tag multi-select with preset values + custom entry input ("Add custom sector..." + "Add" button)

Selected sector chips use Sunbird orange (`#DC7828`) highlight. Form submits all new fields to `POST /auth/register`.

### New: Profile Completion Page (`/complete-profile`)

Standalone page (not inside dashboard layout). Contains:
- Logo + header: "Complete Your Profile"
- Subtitle: "Help us understand how you're using Sunbird AI so we can serve you better."
- Form fields: Full Name, Organization Name, Organization Type, Impact Sectors
- "Save & Continue to Dashboard" button → calls `PUT /auth/profile` → redirects to `/dashboard`
- "Skip for now →" link → navigates directly to `/dashboard`

Route added to `App.tsx` as a `RequireAuth`-wrapped route. Unauthenticated users are redirected to `/login`.

### New: Dashboard Banner

Shown at the top of the Dashboard page when `GET /auth/profile/status` returns `is_complete: false`.

- Orange-tinted gradient background matching Sunbird brand
- User icon + message: "Complete your profile — Add your organization type and impact sectors to help us understand how Sunbird AI is being used."
- "Update Profile" button linking to `/complete-profile`
- Dashboard only — does not appear on API Keys or Account pages
- Disappears automatically once profile is complete (re-checks on mount)
- Non-blocking — all dashboard content renders normally below

### Updated: Account Settings Page (`/account`)

Extend the existing "Profile Information" card with:
1. **Full Name** — text input after Username
2. **Organization Type** — dropdown after Organization
3. **Impact Sectors** — chip multi-select + custom entry after Organization Type

New fields show a temporary orange "New" badge label to draw attention.

"Save Changes" button wired to `PUT /auth/profile` (currently a stub `alert()`).

### Updated: AuthContext

The `user` object in AuthContext must include the new fields (`full_name`, `organization_type`, `sector`) so all pages can access them. `GET /auth/me` already returns the full `User` schema, so this flows automatically once the backend schema is updated.

## Backward Compatibility

- All new DB columns are nullable — existing rows unaffected
- Existing API consumers see no breaking changes (new fields are additive in responses)
- `/setup-organization` endpoint kept working (not removed)
- Existing users with incomplete profiles get a non-blocking banner — nothing crashes, nothing is gated
- `EndpointLog` entries for unauthenticated or old requests have `NULL` for new columns

## Testing

### Backend Tests
- `test_register_with_profile_fields` — registration with new fields succeeds
- `test_register_backward_compat` — old registration payload (without new fields) still succeeds, user created with null profile fields
- `test_update_profile` — `PUT /auth/profile` partial updates work
- `test_update_profile_invalid_org_type` — rejects invalid organization types
- `test_profile_status_complete` — returns `is_complete: true` when all fields present
- `test_profile_status_incomplete` — returns correct `missing_fields`
- `test_endpoint_log_captures_profile_fields` — monitoring middleware logs org type and sector

### Frontend
- Registration form submits new fields correctly
- Profile completion page calls `PUT /auth/profile` and redirects
- "Skip for now" navigates to dashboard without error
- Dashboard banner shows for incomplete profiles, hides for complete ones
- Account Settings saves profile changes via `PUT /auth/profile`
- Build passes: `npm run build` in `frontend/`
- Lint passes: `npm run lint` in `frontend/`
