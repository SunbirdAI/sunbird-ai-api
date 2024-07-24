import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.crud.users import (
    create_user,
    get_user_by_email,
    get_user_by_username,
    update_user_password_reset_token,
)
from app.deps import get_current_user, get_db
from app.models.users import User as DBUser
from app.schemas.users import (
    ChangePassword,
    ForgotPassword,
    ResetPassword,
    Token,
    User,
    UserCreate,
    UserInDB,
)
from app.utils.auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.utils.email_utils import send_password_reset_email

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    hashed_password = get_password_hash(user.password)
    db_user = await get_user_by_username(db, user.username)
    if db_user:
        raise HTTPException(
            status_code=400, detail="Username already taken, choose another username"
        )
    db_user = await get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_db = UserInDB(**user.model_dump(), hashed_password=hashed_password)
    user = await create_user(db, user_db)
    return user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "account_type": user.account_type},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
def read_users_me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
async def request_password_reset(
    request: ForgotPassword, db: AsyncSession = Depends(get_db)
):
    response = {"success": False, "error": True, "message": "Something went wrong!"}
    try:
        user = await get_user_by_email(db, request.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        reset_token = str(uuid.uuid4())

        user = await update_user_password_reset_token(db, user.id, reset_token)
        await send_password_reset_email(
            to_email=request.email, reset_token=user.password_reset_token
        )

        response["message"] = "Password reset email sent"
        response["success"] = True
        response["error"] = False
    except Exception as e:
        print(str(e))
        response["message"] = str(e)
    return response


@router.post("/reset-password")
async def reset_password(request: ResetPassword, db: AsyncSession = Depends(get_db)):
    response = {"success": False, "error": True, "message": "Something went wrong!"}
    try:
        result = await db.execute(
            select(DBUser).filter(DBUser.password_reset_token == request.token)
        )
        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=404, detail="Invalid reset token provided")

        user.hashed_password = get_password_hash(request.new_password)
        user.password_reset_token = None
        await db.commit()

        response["message"] = "Password reset successful"
        response["success"] = True
        response["error"] = False
    except Exception as e:
        print(str(e))
        response["message"] = str(e)
    return response


@router.post("/change-password")
async def change_password(
    request: ChangePassword,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = current_user
    user = await get_user_by_email(db, user.email)
    if not verify_password(request.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong old password given")
    user.hashed_password = get_password_hash(request.new_password)
    await db.commit()

    return {"message": "Password change successful", "success": True}
