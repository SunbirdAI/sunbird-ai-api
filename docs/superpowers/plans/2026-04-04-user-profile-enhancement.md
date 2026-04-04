# User Profile Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full_name, organization_type, and sector fields to user profiles with a profile completion flow, dashboard banner, and endpoint log denormalization.

**Architecture:** Extend the existing User model with 3 nullable columns. Add PUT /auth/profile and GET /auth/profile/status endpoints. Build a frontend profile completion page and dashboard banner. Denormalize new fields into EndpointLog via MonitoringMiddleware.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, React 18, TypeScript, Tailwind CSS, Axios

**Spec:** `docs/superpowers/specs/2026-04-04-user-profile-enhancement-design.md`

---

## File Map

### Backend — Create
- `app/alembic/versions/xxxx_add_profile_fields.py` (auto-generated migration)

### Backend — Modify
- `app/models/users.py` — add full_name, organization_type, sector columns
- `app/models/monitoring.py` — add organization_type, sector columns to EndpointLog
- `app/schemas/users.py` — add ProfileUpdate, ProfileCompletionStatus, update UserBase/UserCreate/User
- `app/crud/users.py` — add update_user_profile()
- `app/routers/auth.py` — add PUT /profile, GET /profile/status, modify register + google callback
- `app/middleware/monitoring_middleware.py` — extract and log new profile fields
- `app/crud/monitoring.py` — pass new fields through to EndpointLog creation
- `app/schemas/monitoring.py` — add organization_type, sector to EndpointLog schema

### Backend — Test
- `app/tests/test_auth.py` — new tests for profile endpoints and registration changes

### Frontend — Create
- `frontend/src/pages/CompleteProfile.tsx` — profile completion page
- `frontend/src/components/ProfileBanner.tsx` — dashboard banner component

### Frontend — Modify
- `frontend/src/context/AuthContext.tsx` — add new fields to User interface
- `frontend/src/App.tsx` — add /complete-profile route
- `frontend/src/pages/Register.tsx` — add new form fields
- `frontend/src/pages/Dashboard.tsx` — add ProfileBanner
- `frontend/src/pages/AccountSettings.tsx` — add new profile fields, wire Save to PUT /auth/profile

---

## Task 1: Add new columns to User model

**Files:**
- Modify: `app/models/users.py:6-16`

- [ ] **Step 1: Add columns to User model**

Add the three new columns after `oauth_type` (line 16):

```python
# In app/models/users.py, add these imports at the top:
from sqlalchemy import Column, Integer, String, JSON

# Add these columns to the User class after oauth_type:
    full_name = Column(String, nullable=True, default=None)
    organization_type = Column(String, nullable=True, default=None)
    sector = Column(JSON, nullable=True, default=None)
```

The full file should look like:

```python
from sqlalchemy import Column, Integer, String, JSON

from app.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String, default=None)
    organization = Column(String, nullable=False, default="Unknown")
    account_type = Column(String, nullable=False, default="Free")
    password_reset_token = Column(String, nullable=True)
    oauth_type = Column(String, nullable=True, default="Credentials")
    full_name = Column(String, nullable=True, default=None)
    organization_type = Column(String, nullable=True, default=None)
    sector = Column(JSON, nullable=True, default=None)
```

- [ ] **Step 2: Commit**

```bash
git add app/models/users.py
git commit -m "feat: add full_name, organization_type, sector columns to User model"
```

---

## Task 2: Add new columns to EndpointLog model

**Files:**
- Modify: `app/models/monitoring.py:7-15`

- [ ] **Step 1: Add columns to EndpointLog model**

Add `organization_type` and `sector` columns. The full file:

```python
from sqlalchemy import Column, DateTime, Float, Integer, String, JSON, func

from app.database.db import Base


class EndpointLog(Base):
    __tablename__ = "endpoint_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    organization = Column(String, index=True)
    endpoint = Column(String, index=True)
    time_taken = Column(Float)
    date = Column(DateTime(timezone=True), server_default=func.now())
    organization_type = Column(String, nullable=True, default=None)
    sector = Column(JSON, nullable=True, default=None)
```

- [ ] **Step 2: Commit**

```bash
git add app/models/monitoring.py
git commit -m "feat: add organization_type, sector columns to EndpointLog model"
```

---

## Task 3: Generate and review Alembic migration

**Files:**
- Create: `app/alembic/versions/xxxx_add_profile_and_log_fields.py` (auto-generated)

- [ ] **Step 1: Generate migration**

```bash
alembic revision --autogenerate -m "add profile fields to users and endpoint_logs"
```

- [ ] **Step 2: Review the generated migration file**

Open the file in `app/alembic/versions/` and verify it contains:
- `op.add_column('users', sa.Column('full_name', sa.String(), nullable=True))`
- `op.add_column('users', sa.Column('organization_type', sa.String(), nullable=True))`
- `op.add_column('users', sa.Column('sector', sa.JSON(), nullable=True))`
- `op.add_column('endpoint_logs', sa.Column('organization_type', sa.String(), nullable=True))`
- `op.add_column('endpoint_logs', sa.Column('sector', sa.JSON(), nullable=True))`

And the downgrade drops those columns.

- [ ] **Step 3: Commit**

```bash
git add app/alembic/versions/
git commit -m "migration: add profile fields to users and endpoint_logs tables"
```

---

## Task 4: Update Pydantic schemas

**Files:**
- Modify: `app/schemas/users.py`

- [ ] **Step 1: Update schemas**

Replace the full contents of `app/schemas/users.py`:

```python
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class AccountType(str, Enum):
    free = "Free"
    premium = "Premium"
    admin = "Admin"


class OAuthType(str, Enum):
    credentials = "Credentials"
    google = "Google"
    github = "GitHub"


ALLOWED_ORGANIZATION_TYPES = [
    "NGO",
    "Government",
    "Private Sector",
    "Research",
    "Individual",
    "Other",
]


class UserBase(BaseModel):
    username: str
    email: EmailStr
    organization: str
    account_type: AccountType = AccountType.free
    oauth_type: OAuthType = OAuthType.credentials
    full_name: Optional[str] = None
    organization_type: Optional[str] = None
    sector: Optional[List[str]] = None


class UserGoogle(BaseModel):
    username: str
    email: EmailStr
    organization: Optional[str] = None
    hashed_password: Optional[str] = None
    account_type: AccountType = AccountType.free
    oauth_type: OAuthType = OAuthType.google
    full_name: Optional[str] = None
    organization_type: Optional[str] = None
    sector: Optional[List[str]] = None


class UserInDB(UserBase):
    hashed_password: Optional[str] = None


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    organization: Optional[str] = None
    organization_type: Optional[str] = None
    sector: Optional[List[str]] = None


class ProfileCompletionStatus(BaseModel):
    is_complete: bool
    missing_fields: List[str]
```

- [ ] **Step 2: Update monitoring schema**

In `app/schemas/monitoring.py`, add the new fields:

```python
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class EndpointLog(BaseModel):
    id: Optional[int] = None
    username: str
    endpoint: str
    organization: Optional[str] = None
    time_taken: float
    date: Optional[datetime] = None
    organization_type: Optional[str] = None
    sector: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 3: Commit**

```bash
git add app/schemas/users.py app/schemas/monitoring.py
git commit -m "feat: add profile and completion status schemas"
```

---

## Task 5: Add update_user_profile CRUD function

**Files:**
- Modify: `app/crud/users.py`
- Test: `app/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `app/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_update_profile(authenticated_client, test_user):
    response = await authenticated_client.put(
        "/auth/profile",
        json={
            "full_name": "Test User Full Name",
            "organization": "Updated Org",
            "organization_type": "Research",
            "sector": ["Health", "Education"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Test User Full Name"
    assert data["organization"] == "Updated Org"
    assert data["organization_type"] == "Research"
    assert data["sector"] == ["Health", "Education"]


@pytest.mark.asyncio
async def test_update_profile_partial(authenticated_client, test_user):
    response = await authenticated_client.put(
        "/auth/profile",
        json={"full_name": "Just A Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Just A Name"
    assert data["organization_type"] is None  # not updated


@pytest.mark.asyncio
async def test_update_profile_invalid_org_type(authenticated_client, test_user):
    response = await authenticated_client.put(
        "/auth/profile",
        json={"organization_type": "InvalidType"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_profile_status_incomplete(authenticated_client, test_user):
    response = await authenticated_client.get("/auth/profile/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_complete"] is False
    assert "full_name" in data["missing_fields"]
    assert "organization_type" in data["missing_fields"]
    assert "sector" in data["missing_fields"]


@pytest.mark.asyncio
async def test_profile_status_complete(authenticated_client, test_user):
    # First complete the profile
    await authenticated_client.put(
        "/auth/profile",
        json={
            "full_name": "Complete User",
            "organization_type": "NGO",
            "sector": ["Health"],
        },
    )
    response = await authenticated_client.get("/auth/profile/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_complete"] is True
    assert data["missing_fields"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest app/tests/test_auth.py::test_update_profile -v
```

Expected: FAIL (endpoint does not exist yet)

- [ ] **Step 3: Add CRUD function**

Add to the end of `app/crud/users.py`:

```python
async def update_user_profile(
    db: AsyncSession, user_id: int, profile_data: dict
) -> User:
    """Update user profile fields. Only updates non-None values."""
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    if not user:
        return None
    for key, value in profile_data.items():
        if value is not None:
            setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user
```

Also add the `select` import if not already present at the top of `app/crud/users.py`:

```python
from sqlalchemy.future import select
```

- [ ] **Step 4: Commit**

```bash
git add app/crud/users.py
git commit -m "feat: add update_user_profile CRUD function"
```

---

## Task 6: Add profile endpoints to auth router

**Files:**
- Modify: `app/routers/auth.py`

- [ ] **Step 1: Add imports at the top of auth.py**

Add these to the existing imports in `app/routers/auth.py`:

```python
from app.crud.users import update_user_profile
from app.schemas.users import (
    ALLOWED_ORGANIZATION_TYPES,
    ProfileCompletionStatus,
    ProfileUpdate,
)
from app.core.exceptions import BadRequestError
```

Note: `BadRequestError` may already be imported — check first. `get_current_user` and `get_db` should already be imported.

- [ ] **Step 2: Add PUT /profile endpoint**

Add after the existing `/change-password` endpoint (around line 178):

```python
@router.put("/profile", response_model=User)
async def update_profile(
    profile_data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate organization_type if provided
    if (
        profile_data.organization_type is not None
        and profile_data.organization_type not in ALLOWED_ORGANIZATION_TYPES
    ):
        raise BadRequestError(
            message=f"Invalid organization type. Must be one of: {', '.join(ALLOWED_ORGANIZATION_TYPES)}"
        )

    # Validate sector if provided
    if profile_data.sector is not None:
        if not isinstance(profile_data.sector, list) or any(
            not isinstance(s, str) or not s.strip() for s in profile_data.sector
        ):
            raise BadRequestError(message="Sector must be a list of non-empty strings")

    update_data = profile_data.model_dump(exclude_unset=True)
    updated_user = await update_user_profile(db, current_user.id, update_data)
    return updated_user
```

- [ ] **Step 3: Add GET /profile/status endpoint**

Add right after the PUT /profile endpoint:

```python
@router.get("/profile/status", response_model=ProfileCompletionStatus)
async def profile_status(current_user: User = Depends(get_current_user)):
    missing_fields = []
    if not current_user.full_name:
        missing_fields.append("full_name")
    if not current_user.organization or current_user.organization == "Unknown":
        missing_fields.append("organization")
    if not current_user.organization_type:
        missing_fields.append("organization_type")
    if not current_user.sector:
        missing_fields.append("sector")

    return ProfileCompletionStatus(
        is_complete=len(missing_fields) == 0,
        missing_fields=missing_fields,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest app/tests/test_auth.py::test_update_profile app/tests/test_auth.py::test_update_profile_partial app/tests/test_auth.py::test_update_profile_invalid_org_type app/tests/test_auth.py::test_profile_status_incomplete app/tests/test_auth.py::test_profile_status_complete -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/auth.py app/tests/test_auth.py
git commit -m "feat: add PUT /auth/profile and GET /auth/profile/status endpoints"
```

---

## Task 7: Update registration to accept new fields

**Files:**
- Modify: `app/routers/auth.py:70-87`
- Test: `app/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `app/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_register_with_profile_fields(async_client, test_db):
    response = await async_client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "organization": "New Org",
            "password": "securepass123",
            "full_name": "New User",
            "organization_type": "NGO",
            "sector": ["Health", "Agriculture"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "New User"
    assert data["organization_type"] == "NGO"
    assert data["sector"] == ["Health", "Agriculture"]


@pytest.mark.asyncio
async def test_register_backward_compat(async_client, test_db):
    response = await async_client.post(
        "/auth/register",
        json={
            "username": "olduser",
            "email": "olduser@example.com",
            "organization": "Old Org",
            "password": "securepass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] is None
    assert data["organization_type"] is None
    assert data["sector"] is None
```

- [ ] **Step 2: Run tests to verify they pass**

The registration endpoint already uses `UserCreate` which now inherits the optional fields from `UserBase`. No code change needed to the register endpoint itself — the schema changes in Task 4 handle this.

```bash
pytest app/tests/test_auth.py::test_register_with_profile_fields app/tests/test_auth.py::test_register_backward_compat -v
```

Expected: Both PASS

- [ ] **Step 3: Commit**

```bash
git add app/tests/test_auth.py
git commit -m "test: add registration tests for new profile fields and backward compat"
```

---

## Task 8: Update Google OAuth callback redirect

**Files:**
- Modify: `app/routers/auth.py:237-245`

- [ ] **Step 1: Update redirect logic**

In `app/routers/auth.py`, find the redirect logic in `google_callback` (around lines 237-245):

```python
        # Determine redirect URL
        redirect_url = (
            f"/setup-organization" if db_user.organization == "Unknown" else "/login"
        )
```

Replace with:

```python
        # Determine redirect URL - redirect to profile completion if profile is incomplete
        profile_incomplete = (
            not db_user.full_name
            or not db_user.organization
            or db_user.organization == "Unknown"
            or not db_user.organization_type
            or not db_user.sector
        )
        redirect_url = "/complete-profile" if profile_incomplete else "/login"
```

- [ ] **Step 2: Commit**

```bash
git add app/routers/auth.py
git commit -m "feat: redirect Google OAuth users to /complete-profile when profile incomplete"
```

---

## Task 9: Update MonitoringMiddleware to log profile fields

**Files:**
- Modify: `app/middleware/monitoring_middleware.py:133-193` (user extraction)
- Modify: `app/middleware/monitoring_middleware.py:195-243` (log writing)
- Modify: `app/crud/monitoring.py:34-58`

- [ ] **Step 1: Update _extract_user_info to return new fields**

In `app/middleware/monitoring_middleware.py`, update the return dict in `_extract_user_info` (around line 186-189):

Replace:
```python
                return {
                    "username": user.username,
                    "organization": user.organization,
                }
```

With:
```python
                return {
                    "username": user.username,
                    "organization": user.organization,
                    "organization_type": user.organization_type,
                    "sector": user.sector,
                }
```

- [ ] **Step 2: Update _log_request_data to pass new fields**

In `_log_request_data` (around line 195), update the method signature and the User object creation.

Replace the method signature (lines 195-202):
```python
    async def _log_request_data(
        self,
        username: str,
        organization: Optional[str],
        endpoint: str,
        start_time: float,
        end_time: float,
    ) -> None:
```

With:
```python
    async def _log_request_data(
        self,
        username: str,
        organization: Optional[str],
        endpoint: str,
        start_time: float,
        end_time: float,
        organization_type: Optional[str] = None,
        sector: Optional[list] = None,
    ) -> None:
```

Then update the User object creation (around line 227):

Replace:
```python
                user = User(username=username, organization=organization)
```

With:
```python
                user = User(
                    username=username,
                    organization=organization,
                    organization_type=organization_type,
                    sector=sector,
                )
```

- [ ] **Step 3: Update the dispatch method to pass new fields**

In the `dispatch` method, find where `_log_request_data` is called and ensure it passes the new fields from `user_info`. The call should look like:

```python
                await self._log_request_data(
                    username=user_info["username"],
                    organization=user_info.get("organization"),
                    endpoint=request.url.path,
                    start_time=start_time,
                    end_time=end_time,
                    organization_type=user_info.get("organization_type"),
                    sector=user_info.get("sector"),
                )
```

- [ ] **Step 4: Update create_endpoint_log in crud/monitoring.py**

In `app/crud/monitoring.py`, update `create_endpoint_log` (lines 34-43) to pass new fields:

Replace:
```python
async def create_endpoint_log(log: schemas.EndpointLog, db: AsyncSession):
    logging.info(f"log: {log}")
    db_log = models.EndpointLog(
        username=log.username,
        endpoint=log.endpoint,
        time_taken=log.time_taken,
        organization=log.organization,
    )
    db.add(db_log)
    await db.commit()
```

With:
```python
async def create_endpoint_log(log: schemas.EndpointLog, db: AsyncSession):
    logging.info(f"log: {log}")
    db_log = models.EndpointLog(
        username=log.username,
        endpoint=log.endpoint,
        time_taken=log.time_taken,
        organization=log.organization,
        organization_type=log.organization_type,
        sector=log.sector,
    )
    db.add(db_log)
    await db.commit()
```

- [ ] **Step 5: Update log_endpoint to pass new fields from User**

In `app/crud/monitoring.py`, update `log_endpoint` (lines 46-58):

Replace:
```python
async def log_endpoint(
    db: AsyncSession, user: User, request: Request, start_time: float, end_time: float
):
    try:
        endpoint_log = EndpointLog(
            username=user.username,
            endpoint=request.url.path,
            organization=user.organization,
            time_taken=(end_time - start_time),
        )
        await create_endpoint_log(endpoint_log, db)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
```

With:
```python
async def log_endpoint(
    db: AsyncSession, user: User, request: Request, start_time: float, end_time: float
):
    try:
        endpoint_path = request.url.path if request else "unknown"
        endpoint_log = EndpointLog(
            username=user.username,
            endpoint=endpoint_path,
            organization=user.organization,
            time_taken=(end_time - start_time),
            organization_type=getattr(user, "organization_type", None),
            sector=getattr(user, "sector", None),
        )
        await create_endpoint_log(endpoint_log, db)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
```

- [ ] **Step 6: Commit**

```bash
git add app/middleware/monitoring_middleware.py app/crud/monitoring.py app/schemas/monitoring.py
git commit -m "feat: log organization_type and sector in EndpointLog via monitoring middleware"
```

---

## Task 10: Run all backend tests and lint

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

```bash
pytest app/tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Run linting**

```bash
make lint-check
```

If there are formatting issues:

```bash
make lint-apply
```

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -u
git commit -m "style: apply lint formatting"
```

---

## Task 11: Update frontend AuthContext with new User fields

**Files:**
- Modify: `frontend/src/context/AuthContext.tsx:4-10`

- [ ] **Step 1: Update User interface**

In `frontend/src/context/AuthContext.tsx`, replace the `User` interface (lines 4-10):

```typescript
interface User {
  username: string;
  email: string;
  organization?: string;
  account_type?: string;
  oauth_type?: string;
  full_name?: string;
  organization_type?: string;
  sector?: string[];
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/context/AuthContext.tsx
git commit -m "feat: add profile fields to frontend User interface"
```

---

## Task 12: Update Registration form with new fields

**Files:**
- Modify: `frontend/src/pages/Register.tsx`

- [ ] **Step 1: Add constants and state**

At the top of `Register.tsx`, after imports, add:

```typescript
const ORGANIZATION_TYPES = ['NGO', 'Government', 'Private Sector', 'Research', 'Individual', 'Other'];
const PRESET_SECTORS = ['Health', 'Agriculture', 'Energy', 'Environment', 'Education', 'Governance'];
```

Update the `formData` state (around line 7-13) to include new fields:

```typescript
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    full_name: '',
    organization: '',
    organization_type: '',
    password: '',
    confirmPassword: '',
  });
  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);
  const [customSector, setCustomSector] = useState('');
```

- [ ] **Step 2: Update handleSubmit to send new fields**

Replace the axios.post call inside `handleSubmit` (around line 32-37):

```typescript
      await axios.post('/auth/register', {
        username: formData.username,
        email: formData.email,
        organization: formData.organization,
        password: formData.password,
        full_name: formData.full_name || undefined,
        organization_type: formData.organization_type || undefined,
        sector: selectedSectors.length > 0 ? selectedSectors : undefined,
      });
```

- [ ] **Step 3: Add helper functions**

Add before the return statement:

```typescript
  const toggleSector = (sector: string) => {
    setSelectedSectors((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]
    );
  };

  const addCustomSector = () => {
    const trimmed = customSector.trim();
    if (trimmed && !selectedSectors.includes(trimmed)) {
      setSelectedSectors((prev) => [...prev, trimmed]);
      setCustomSector('');
    }
  };
```

- [ ] **Step 4: Add new form fields in the JSX**

Add the `Building` import to also import `Briefcase` and `Target` from lucide-react:

```typescript
import { User, Mail, Building, Lock, Loader2, Eye, EyeOff, Briefcase, Target } from 'lucide-react';
```

After the Organization input field and before the Password field, add these three new fields:

**Full Name field** (after Email, before Organization):

```tsx
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Full Name <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  className="w-full pl-10 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="John Doe"
                  disabled={loading}
                />
              </div>
            </div>
```

**Organization Type field** (after Organization):

```tsx
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Organization Type
              </label>
              <div className="relative">
                <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <select
                  required
                  value={formData.organization_type}
                  onChange={(e) => setFormData({ ...formData, organization_type: e.target.value })}
                  className="w-full pl-10 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white appearance-none"
                  disabled={loading}
                >
                  <option value="">Select type...</option>
                  {ORGANIZATION_TYPES.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
            </div>
```

**Impact Sectors field** (after Organization Type):

```tsx
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Impact Sectors <span className="text-gray-400 font-normal">(select all that apply)</span>
              </label>
              <div className="flex flex-wrap gap-2 mt-2">
                {[...PRESET_SECTORS, ...selectedSectors.filter((s) => !PRESET_SECTORS.includes(s))].map((sector) => (
                  <button
                    key={sector}
                    type="button"
                    onClick={() => toggleSector(sector)}
                    disabled={loading}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      selectedSectors.includes(sector)
                        ? 'border-primary-500 bg-primary-500/10 text-primary-600 dark:text-primary-400'
                        : 'border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'
                    }`}
                  >
                    {sector} {selectedSectors.includes(sector) && '✓'}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 mt-2">
                <input
                  type="text"
                  value={customSector}
                  onChange={(e) => setCustomSector(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomSector())}
                  className="flex-1 px-3 py-1.5 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white text-sm placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="Add custom sector..."
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={addCustomSector}
                  disabled={loading}
                  className="px-3 py-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Add
                </button>
              </div>
            </div>
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Register.tsx
git commit -m "feat: add profile fields to registration form"
```

---

## Task 13: Create ProfileBanner component

**Files:**
- Create: `frontend/src/components/ProfileBanner.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ProfileBanner.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { User } from 'lucide-react';
import axios from 'axios';

export default function ProfileBanner() {
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    const checkProfileStatus = async () => {
      try {
        const response = await axios.get('/auth/profile/status');
        setShowBanner(!response.data.is_complete);
      } catch {
        setShowBanner(false);
      }
    };
    checkProfileStatus();
  }, []);

  if (!showBanner) return null;

  return (
    <div className="bg-gradient-to-r from-primary-500/10 to-primary-500/5 border border-primary-500/20 rounded-xl p-4 mb-6 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 flex-1">
        <div className="w-9 h-9 rounded-lg bg-primary-500/15 flex items-center justify-center flex-shrink-0">
          <User className="w-[18px] h-[18px] text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">
            Complete your profile
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Add your organization type and impact sectors to help us understand how Sunbird AI is being used.
          </p>
        </div>
      </div>
      <Link
        to="/complete-profile"
        className="px-5 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm shadow-primary-500/20 whitespace-nowrap"
      >
        Update Profile
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ProfileBanner.tsx
git commit -m "feat: create ProfileBanner component for incomplete profile notification"
```

---

## Task 14: Add ProfileBanner to Dashboard

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Import and add banner**

At the top of `frontend/src/pages/Dashboard.tsx`, add the import:

```typescript
import ProfileBanner from '../components/ProfileBanner';
```

In the return JSX (around line 294), add `<ProfileBanner />` right after the opening `<div className="space-y-6">` and before the Header section:

```tsx
    <div className="space-y-6">
      <ProfileBanner />

      {/* Header */}
```

Also add `<ProfileBanner />` in the loading skeleton return (around line 214), right after `<div className="space-y-6 ">`:

```tsx
      <div className="space-y-6 ">
        <ProfileBanner />

        {/* Header Skeleton */}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add profile completion banner to dashboard"
```

---

## Task 15: Create CompleteProfile page

**Files:**
- Create: `frontend/src/pages/CompleteProfile.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the page component**

Create `frontend/src/pages/CompleteProfile.tsx`:

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const ORGANIZATION_TYPES = ['NGO', 'Government', 'Private Sector', 'Research', 'Individual', 'Other'];
const PRESET_SECTORS = ['Health', 'Agriculture', 'Energy', 'Environment', 'Education', 'Governance'];

export default function CompleteProfile() {
  const { user, checkAuth } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    full_name: user?.full_name || '',
    organization: user?.organization === 'Unknown' ? '' : (user?.organization || ''),
    organization_type: user?.organization_type || '',
  });
  const [selectedSectors, setSelectedSectors] = useState<string[]>(user?.sector || []);
  const [customSector, setCustomSector] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggleSector = (sector: string) => {
    setSelectedSectors((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]
    );
  };

  const addCustomSector = () => {
    const trimmed = customSector.trim();
    if (trimmed && !selectedSectors.includes(trimmed)) {
      setSelectedSectors((prev) => [...prev, trimmed]);
      setCustomSector('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await axios.put('/auth/profile', {
        full_name: formData.full_name || undefined,
        organization: formData.organization || undefined,
        organization_type: formData.organization_type || undefined,
        sector: selectedSectors.length > 0 ? selectedSectors : undefined,
      });
      await checkAuth();
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-black px-4 py-12">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <img
            src="/logo.png"
            alt="Sunbird AI"
            className="h-10 w-10 rounded-full object-cover mx-auto mb-3"
          />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Complete Your Profile
          </h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Help us understand how you're using Sunbird AI so we can serve you better.
          </p>
        </div>

        <div className="bg-white dark:bg-secondary rounded-2xl shadow-lg dark:shadow-lg dark:shadow-black/10 p-8 border border-gray-100 dark:border-white/5">
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Full Name
              </label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                placeholder="John Doe"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Organization Name
              </label>
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
                placeholder="Sunbird AI"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Organization Type
              </label>
              <select
                value={formData.organization_type}
                onChange={(e) => setFormData({ ...formData, organization_type: e.target.value })}
                className="w-full px-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white appearance-none"
                disabled={loading}
              >
                <option value="">Select type...</option>
                {ORGANIZATION_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Impact Sectors <span className="text-gray-400 font-normal">(select all that apply)</span>
              </label>
              <div className="flex flex-wrap gap-2 mt-2">
                {[...PRESET_SECTORS, ...selectedSectors.filter((s) => !PRESET_SECTORS.includes(s))].map((sector) => (
                  <button
                    key={sector}
                    type="button"
                    onClick={() => toggleSector(sector)}
                    disabled={loading}
                    className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      selectedSectors.includes(sector)
                        ? 'border-primary-500 bg-primary-500/10 text-primary-600 dark:text-primary-400'
                        : 'border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'
                    }`}
                  >
                    {sector} {selectedSectors.includes(sector) && '✓'}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 mt-2">
                <input
                  type="text"
                  value={customSector}
                  onChange={(e) => setCustomSector(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomSector())}
                  className="flex-1 px-3 py-1.5 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white text-sm placeholder-gray-400 dark:placeholder-gray-600"
                  placeholder="Add custom sector..."
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={addCustomSector}
                  disabled={loading}
                  className="px-3 py-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Add
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors shadow-lg shadow-primary-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Saving...' : 'Save & Continue to Dashboard'}
            </button>
          </form>

          <div className="mt-4 text-center">
            <button
              onClick={() => navigate('/dashboard')}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
            >
              Skip for now →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.tsx**

In `frontend/src/App.tsx`, add the import at the top:

```typescript
import CompleteProfile from './pages/CompleteProfile';
```

Add the route inside `AppRoutes`, after the `/setup-organization` route (around line 47) and before the `/dashboard` route:

```tsx
      <Route
        path="/complete-profile"
        element={
          <RequireAuth>
            <PageTitle title="Complete Profile">
              <CompleteProfile />
            </PageTitle>
          </RequireAuth>
        }
      />
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CompleteProfile.tsx frontend/src/App.tsx
git commit -m "feat: add profile completion page at /complete-profile"
```

---

## Task 16: Update Account Settings with profile fields

**Files:**
- Modify: `frontend/src/pages/AccountSettings.tsx`

- [ ] **Step 1: Add constants, imports, and state**

Add imports at the top of `AccountSettings.tsx`:

```typescript
import { User, Mail, Lock, Moon, Sun, Laptop, CreditCard, Eye, EyeOff, Building, Briefcase, Target } from 'lucide-react';
```

Add constants after imports:

```typescript
const ORGANIZATION_TYPES = ['NGO', 'Government', 'Private Sector', 'Research', 'Individual', 'Other'];
const PRESET_SECTORS = ['Health', 'Agriculture', 'Energy', 'Environment', 'Education', 'Governance'];
```

Update the formData state (around line 10-13) to include new fields:

```typescript
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    organization: user?.organization || '',
    organization_type: user?.organization_type || '',
  });
  const [selectedSectors, setSelectedSectors] = useState<string[]>(user?.sector || []);
  const [customSector, setCustomSector] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');
  const [profileError, setProfileError] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);
```

- [ ] **Step 2: Add helper functions and update handleSubmit**

Add sector toggle/add helpers and replace `handleSubmit` (around line 27-31):

```typescript
  const toggleSector = (sector: string) => {
    setSelectedSectors((prev) =>
      prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]
    );
  };

  const addCustomSector = () => {
    const trimmed = customSector.trim();
    if (trimmed && !selectedSectors.includes(trimmed)) {
      setSelectedSectors((prev) => [...prev, trimmed]);
      setCustomSector('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess('');
    setProfileLoading(true);

    try {
      await axios.put('/auth/profile', {
        full_name: formData.full_name || undefined,
        organization: formData.organization || undefined,
        organization_type: formData.organization_type || undefined,
        sector: selectedSectors.length > 0 ? selectedSectors : undefined,
      });
      setProfileSuccess('Profile updated successfully!');
    } catch (err: any) {
      setProfileError(err.response?.data?.detail || 'Failed to update profile.');
    } finally {
      setProfileLoading(false);
    }
  };
```

Remove the `console.log(user);` line (line 14 in original).

- [ ] **Step 3: Add new fields to the form JSX**

Inside the Profile Information form, add success/error messages after the opening `<form>` tag:

```tsx
            {profileError && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
                {profileError}
              </div>
            )}
            {profileSuccess && (
              <div className="bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 p-3 rounded-lg text-sm">
                {profileSuccess}
              </div>
            )}
```

After the Username field and before the Email field, add **Full Name**:

```tsx
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Full Name
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                placeholder="John Doe"
                disabled={profileLoading}
              />
            </div>
          </div>
```

After the Email field, add **Organization** (editable):

```tsx
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Organization
            </label>
            <div className="relative">
              <Building className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
                placeholder="Organization Name"
                disabled={profileLoading}
              />
            </div>
          </div>
```

After Organization, add **Organization Type**:

```tsx
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Organization Type
            </label>
            <div className="relative">
              <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <select
                value={formData.organization_type}
                onChange={(e) => setFormData({ ...formData, organization_type: e.target.value })}
                className="w-full pl-9 pr-4 py-2 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white appearance-none"
                disabled={profileLoading}
              >
                <option value="">Select type...</option>
                {ORGANIZATION_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>
          </div>
```

After Organization Type, add **Impact Sectors**:

```tsx
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Impact Sectors
            </label>
            <div className="flex flex-wrap gap-2 mt-1">
              {[...PRESET_SECTORS, ...selectedSectors.filter((s) => !PRESET_SECTORS.includes(s))].map((sector) => (
                <button
                  key={sector}
                  type="button"
                  onClick={() => toggleSector(sector)}
                  disabled={profileLoading}
                  className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                    selectedSectors.includes(sector)
                      ? 'border-primary-500 bg-primary-500/10 text-primary-600 dark:text-primary-400'
                      : 'border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5'
                  }`}
                >
                  {sector} {selectedSectors.includes(sector) && '✓'}
                </button>
              ))}
            </div>
            <div className="flex gap-2 mt-2">
              <input
                type="text"
                value={customSector}
                onChange={(e) => setCustomSector(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomSector())}
                className="flex-1 px-3 py-1.5 bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white text-sm placeholder-gray-400 dark:placeholder-gray-600"
                placeholder="Add custom sector..."
                disabled={profileLoading}
              />
              <button
                type="button"
                onClick={addCustomSector}
                disabled={profileLoading}
                className="px-3 py-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Add
              </button>
            </div>
          </div>
```

Update the Save Changes button to show loading state:

```tsx
          <div className="pt-2">
            <button
              type="submit"
              disabled={profileLoading}
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {profileLoading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AccountSettings.tsx
git commit -m "feat: add profile fields to Account Settings and wire Save to PUT /auth/profile"
```

---

## Task 17: Final verification — full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

```bash
pytest app/tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: Run backend lint**

```bash
make lint-check
```

If issues:
```bash
make lint-apply
```

- [ ] **Step 3: Run frontend build and lint**

```bash
cd frontend && npm run build && npm run lint
```

Expected: Both pass

- [ ] **Step 4: Run npm audit**

```bash
cd frontend && npm audit
```

Review any high/critical vulnerabilities.

- [ ] **Step 5: Commit any remaining fixes**

```bash
git add -u
git commit -m "chore: final lint and build fixes for profile enhancement"
```
