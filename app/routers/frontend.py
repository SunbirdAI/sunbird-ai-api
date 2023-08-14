from fastapi import APIRouter, Request, Form, Depends, responses, status
from fastapi.templating import Jinja2Templates
from app.deps import get_db
from app.utils.auth_utils import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from sqlalchemy.orm import Session
from datetime import timedelta

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
