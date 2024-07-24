from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.users import get_user_by_username
from app.database.db import async_session_maker
from app.schemas.users import TokenData, User
from app.utils.auth_utils import get_username_from_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_db():
    async with async_session_maker() as db_session:
        yield db_session


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        username = get_username_from_token(token)
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(db, token_data.username)
    if user is None:
        raise credentials_exception
    return User.model_validate(user)
