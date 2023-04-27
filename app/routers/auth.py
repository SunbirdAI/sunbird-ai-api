from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models.users import UserCreate, User, UserBase, UserInDB, Token, TokenData
from app.database.db import db, insert_user, get_user
from app.utils.auth_utils import (
    authenticate_user,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    SECRET_KEY,
    ALGORITHM
)
from jose import jwt, JWTError

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate) -> User:
    hashed_password = get_password_hash(user.password)
    # TODO: Implement validation

    user_db = UserInDB(**user.dict(), hashed_password=hashed_password)
    user = insert_user(user_db)
    print(db)
    return user


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserBase:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = UserBase(**get_user(token_data.username).dict())
    return user


@router.get("/me")
async def read_users_me(current_user=Depends(get_current_user)):
    return current_user
