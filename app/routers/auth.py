import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

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
def register(user: UserCreate, db: Session = Depends(get_db)) -> User:
    hashed_password = get_password_hash(user.password)
    db_user = get_user_by_username(db, user.username)
    if db_user:
        raise HTTPException(
            status_code=400, detail="Username already taken, choose another username"
        )
    db_user = get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_db = UserInDB(**user.dict(), hashed_password=hashed_password)
    user = create_user(db, user_db)
    return user


@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
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
    request: ForgotPassword, db: Session = Depends(get_db)
):
    response = {"success": False, "error": True, "message": "Something wong happened!"}
    try:
        user = get_user_by_email(db, request.email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        reset_token = str(uuid.uuid4())

        user = update_user_password_reset_token(db, user.id, reset_token)
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
async def reset_password(request: ResetPassword, db: Session = Depends(get_db)):
    response = {"success": False, "error": True, "message": "Something wong happened!"}
    try:
        user = (
            db.query(DBUser)
            .filter(DBUser.password_reset_token == request.token)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="Invalid reset token provided")

        user.hashed_password = get_password_hash(request.new_password)
        user.password_reset_token = None
        db.commit()

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
    db: Session = Depends(get_db),
):
    user = current_user
    user = get_user_by_email(db, user.email)
    if not verify_password(request.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong old password given")
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()

    return {"message": "Password change successful", "success": True}
