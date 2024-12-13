from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class AccountType(str, Enum):
    free = "Free"
    premium = "Premium"
    admin = "Admin"


class OAuthType(str, Enum):
    credentials = 'Credentials'
    google = 'Google'
    github = 'GitHub'


class UserBase(BaseModel):
    username: str
    email: EmailStr
    organization: str
    account_type: AccountType = AccountType.free
    oauth_type: OAuthType = OAuthType.credentials


class UserGoogle(UserBase):
    username: str
    email: EmailStr
    organization: Optional[str] = None
    hashed_password: Optional[str] = None
    account_type: AccountType = AccountType.free
    oauth_type: OAuthType = OAuthType.google


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
