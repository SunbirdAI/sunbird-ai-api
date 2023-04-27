from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.models.users import UserCreate, User, UserInDB, Token
from app.database.db import db, insert_user
from app.utils.auth_utils import authenticate_user

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate) -> User:
    hashed_password = f'hashed_{user.password}'  # TODO: Implement the actual hashing
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

    # TODO: Implement actual access token generation
    return {
        "access_token": "random_access_token",
        "token_type": "bearer"
    }


async def get_current_user(token: str = Depends(oauth2_scheme)):
    print(f"The token is: {token}")
    return {
        "username": "random_user"
    }

@router.get("/me")
async def read_users_me(current_user = Depends(get_current_user)):
    return current_user
