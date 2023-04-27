from pydantic import BaseModel, EmailStr

class User(BaseModel):
    username: str
    email: EmailStr


class UserInDB(User):
    id: int
    hashed_password: str


class UserCreate(User):
    password: str
