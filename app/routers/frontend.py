import json
import logging
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, responses, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.audio_transcription import (
    get_audio_transcription as crud_audio_transcription,
)
from app.crud.audio_transcription import (
    get_audio_transcriptions as crud_audio_transcriptions,
)
from app.crud.users import create_user, get_user_by_email, get_user_by_username
from app.deps import get_db
from app.routers.auth import get_current_user
from app.schemas.audio_transcription import AudioTranscriptionBase, ItemQueryParams
from app.schemas.users import User, UserCreate, UserInDB
from app.utils.auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    OAuth2PasswordBearerWithCookie,
    authenticate_user,
    create_access_token,
    get_password_hash,
    get_username_from_token,
)
from app.utils.monitoring_utils import aggregate_usage_for_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="/auth/token")
logging.basicConfig(level=logging.INFO)


@router.get("/")
async def home(
    request: Request,
    token: Optional[str] = Depends(
        OAuth2PasswordBearerWithCookie(tokenUrl="/auth/token", auto_error=False)
    ),
):
    if not token:  # if token is invalid or not present
        # Redirect to login page
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    context = {"request": request}
    return templates.TemplateResponse("home.html", context)


@router.get("/login")
async def login(request: Request):  # type: ignore
    context = {"request": request}
    return templates.TemplateResponse("auth/login.html", context)


@router.get("/privacy_policy")
async def privacy_policy(request: Request):  # type: ignore
    context = {"request": request}
    return templates.TemplateResponse("privacy_policy.html", context)


@router.get("/terms_of_service")
async def terms_of_service(request: Request):  # type: ignore
    context = {"request": request}
    return templates.TemplateResponse("terms_of_service.html", context)


@router.get("/setup-organization")
async def setup_organization(request: Request):
    return templates.TemplateResponse("setup_organization.html", {"request": request})


@router.post("/login")
async def login(  # noqa F811
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    errors = []
    user = await authenticate_user(db, username, password)
    if not user:
        errors.append("Incorrect username or password")
        context = {"request": request, "errors": errors}
        return templates.TemplateResponse("auth/login.html", context)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "account_type": user.account_type},
        expires_delta=access_token_expires,
    )
    response = responses.RedirectResponse(
        "/?alert=Successfully Logged In", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response


@router.get("/register")
async def signup(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("auth/register.html", context)


@router.post("/register")
async def signup(  # noqa F811
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    organization: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    errors = []
    if password != confirm_password:
        errors.append("Passwords don't match")
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "errors": errors}
        )

    try:
        user = UserCreate(
            username=username, email=email, organization=organization, password=password
        )
        db_user = await get_user_by_username(db, user.username)
        if db_user:
            errors.append("Username already taken, choose another username")
            return templates.TemplateResponse(
                "auth/register.html", {"request": request, "errors": errors}
            )
        db_user = await get_user_by_email(db, user.email)
        if db_user:
            errors.append("Email already registered")
            return templates.TemplateResponse(
                "auth/register.html", {"request": request, "errors": errors}
            )
        hashed_password = get_password_hash(password)
        user_db = UserInDB(**user.model_dump(), hashed_password=hashed_password)
        await create_user(db, user_db)
        return responses.RedirectResponse(
            "/login?alert=Successfully%20Registered", status_code=status.HTTP_302_FOUND
        )
    except ValidationError as e:
        errors_list = json.loads(e.json())
        for item in errors_list:
            errors.append(item.get("loc")[0] + ": " + item.get("msg"))
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "errors": errors}
        )


@router.get("/logout")
async def logout(_: Request):
    response = responses.RedirectResponse("/login", status_code=302)
    response.delete_cookie(key="access_token")
    return response


@router.get("/tokens")
async def tokens(request: Request, _: str = Depends(oauth2_scheme)):
    context = {"request": request, "token": request.cookies.get("access_token")}
    return templates.TemplateResponse("token_page.html", context=context)


@router.get("/account")
async def account(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    username = get_username_from_token(token)
    user = User.model_validate(await get_user_by_username(db, username))
    aggregates = await aggregate_usage_for_user(db, username)
    context = {
        "request": request,
        "username": username,
        "organization": user.organization,
        "account_type": user.account_type.value,
        "aggregates": aggregates,
    }
    return templates.TemplateResponse("account_page.html", context=context)


@router.get(
    "/transcriptions",
    response_model=List[AudioTranscriptionBase],
)
async def get_audio_transcriptions(
    current_user=Depends(get_current_user),
    params: ItemQueryParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    This endpoint returns all the transcriptions per user.
    It returns the id, username, email, audio_file_url, filename,
    uploaded(time) and the transcription.
    """

    transcriptions = await crud_audio_transcriptions(
        db=db, username=current_user.username, params=params
    )

    if not transcriptions:
        raise HTTPException(status_code=404, detail="No transcriptions found")

    transcriptions_dicts = [t.to_dict() for t in transcriptions]

    return transcriptions_dicts


@router.get("/transcriptions/{id}", response_model=AudioTranscriptionBase)
async def get_audio_transcription(
    id: int, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    This endpoint returns the transcriptions per user_id that is supplied in the Request Body.
    """

    transcription = await crud_audio_transcription(db, id, current_user.username)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    return transcription.to_dict()


@router.put("/transcriptions/{id}", response_model=AudioTranscriptionBase)
async def update_audio_transcription(
    id: int,
    transcription_text: str = Form(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    This endpoint enables us to update the transcription to a new/better transcription.
    This will enable the users to be able to update transcriptions.
    """

    transcription = await crud_audio_transcription(db, id, current_user.username)

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    transcription.transcription = transcription_text
    try:
        await db.commit()
        await db.refresh(transcription)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500, detail="An error occurred while updating the transcription"
        )

    return transcription.to_dict()
