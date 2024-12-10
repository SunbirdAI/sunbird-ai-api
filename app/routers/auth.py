import os
import uuid
import logging
from datetime import timedelta

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette.config import Config

from app.crud.users import (
    create_user,
    get_user_by_email,
    get_user_by_username,
    # update_user_organization,
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
    UserGoogle,
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
oauth = OAuth()

load_dotenv()

# Initialize OAuth with proper configuration
config = Config(".env")
oauth = OAuth(config)

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    client_kwargs={
        "scope": "openid email profile",
        "prompt": "select_account",  # Forces Google account selection
    },
)


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
        if not user or user.oauth_type != 'Credentials':
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

        if not user or user.oauth_type != 'Credentials':
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
    if user.oauth_type == 'Credentials':
        if not verify_password(request.old_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Wrong old password given")
        user.hashed_password = get_password_hash(request.new_password)
        await db.commit()

        return {"message": "Password change successful", "success": True}

    return {"message": "Password change failed", "success": False}


@router.get("/google/login", name="auth:google_login")
async def google_login(request: Request):
    # Get the redirect URI from the request
    redirect_uri = request.url_for("auth:google_callback")
    if os.getenv("ENVIRONMENT") != 'development':
        redirect_uri = redirect_uri.replace("http", "https")

    # Store the intended destination in session
    request.session["next"] = str(request.query_params.get("next", "/"))

    # Redirect to Google login
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="auth:google_callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        # Get token from Google
        token = await oauth.google.authorize_access_token(request)

        # Get user info from Google
        user_info = token.get("userinfo")
        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )

        # Extract user details
        email = user_info["email"]
        username = email.split("@")[0]

        # Check if user exists
        db_user = await get_user_by_email(db, email)
        is_new_user = False

        if not db_user:
            # Create new user
            user_data = UserGoogle(
                email=email,
                username=username,
            )
            db_user = await create_user(db, user_data)
            is_new_user = True

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user in database",
            )

        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": db_user.username, "account_type": db_user.account_type},
            expires_delta=access_token_expires,
        )

        # Determine redirect URL
        redirect_url = f"/setup-organization" if db_user.organization == 'Unknown' else "/"

        # Include token in header response
        response = RedirectResponse(url=redirect_url)

        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            secure=True,  # Ensure secure=True in production
            samesite="lax",
        )

        return response

    except Exception as e:
        logging.error(f"Error during Google callback: {e}")
        return RedirectResponse(url="/login?error=google_auth_failed")
