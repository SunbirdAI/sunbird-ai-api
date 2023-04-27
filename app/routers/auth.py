from fastapi import APIRouter, HTTPException, status
from app.models.users import UserCreate, User, UserInDB
from app.database.db import db, insert_user

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate) -> User:
    hashed_password = f'hashed_{user.password}'  # TODO: Implement the actual hashing
    # TODO: Implement validation

    user_db = UserInDB(**user.dict(), hashed_password=hashed_password)
    user = insert_user(user_db)
    print(db)
    return user
