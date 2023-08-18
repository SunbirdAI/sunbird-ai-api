import json

from fastapi import APIRouter, Request, Form, Depends, responses, status
from fastapi.templating import Jinja2Templates
from app.deps import get_db
from app.utils.auth_utils import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash
from sqlalchemy.orm import Session
from datetime import timedelta
from app.schemas.users import UserCreate, UserInDB
from app.crud.users import create_user, get_user_by_username, get_user_by_email
from pydantic.error_wrappers import ValidationError

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def home(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("home.html", context)


@router.get("/login")
async def login(request: Request): # type: ignore
    context = {"request": request}
    return templates.TemplateResponse("auth/login.html", context)


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    errors = []
    user = authenticate_user(db, username, password)
    if not user:
        errors.append("Incorrect username or password")
        context = {
            "request": request,
            "errors": errors
        }
        return templates.TemplateResponse("auth/login.html", context)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    response = responses.RedirectResponse("/?alert=Successfully Logged In", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response


@router.get("/register")
async def signup(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("auth/register.html", context)


@router.post("/register")
async def signup(request: Request,
                 email: str = Form(...),
                 username: str = Form(...),
                 organization: str = Form(...),
                 password: str = Form(...),
                 confirm_password: str = Form(...),
                 db: Session = Depends(get_db)):
    errors = []
    if password != confirm_password:
        errors.append("Passwords don't match")
        return templates.TemplateResponse("auth/register.html", {"request": request, "errors": errors})

    try:
        user = UserCreate(username=username, email=email, organization=organization, password=password)
        db_user = get_user_by_username(db, user.username)
        if db_user:
            errors.append("Username already taken, choose another username")
            return templates.TemplateResponse("auth/register.html", {"request": request, "errors": errors})
        db_user = get_user_by_email(db, user.email)
        if db_user:
            errors.append("Email already registered")
            return templates.TemplateResponse("auth/register.html", {"request": request, "errors": errors})
        hashed_password = get_password_hash(password)
        user_db = UserInDB(**user.dict(), hashed_password=hashed_password)
        create_user(db, user_db)
        return responses.RedirectResponse("/login?alert=Successfully%20Registered", status_code=status.HTTP_302_FOUND)
    except ValidationError as e:
        errors_list = json.loads(e.json())
        for item in errors_list:
            errors.append(item.get("loc")[0] + ": " + item.get("msg"))
        return templates.TemplateResponse("auth/register.html", {"request": request, "errors": errors})