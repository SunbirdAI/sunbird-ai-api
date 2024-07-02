from enum import Enum

from pydantic import BaseModel, EmailStr


class AccountType(str, Enum):
    free = "Free"
    premium = "Premium"
    admin = "Admin"


class UserBase(BaseModel):
    username: str
    email: EmailStr
    organization: str
    account_type: AccountType = AccountType.free


class UserInDB(UserBase):
    hashed_password: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int

    class Config:
        orm_mode = True
        from_attributes = True


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
