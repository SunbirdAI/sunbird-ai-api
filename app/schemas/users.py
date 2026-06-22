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
