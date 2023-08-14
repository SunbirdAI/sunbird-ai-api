from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def home(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("base.html", context)


@router.get("/login")
async def login(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("auth/login.html", context)


@router.get("/register")
async def signup(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("auth/register.html", context)
