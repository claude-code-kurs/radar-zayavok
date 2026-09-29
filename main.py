import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import COOKIE_NAME, check_password, check_session, make_session
from db import get_requests

load_dotenv()

CABINET_LOGIN = os.getenv("CABINET_LOGIN", "")
CABINET_PASSWORD_HASH = os.getenv("CABINET_PASSWORD_HASH", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"year": datetime.now().year},
    )


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.post("/login")
def login_submit(request: Request, login: str = Form(), password: str = Form()):
    if login == CABINET_LOGIN and check_password(password, CABINET_PASSWORD_HASH):
        response = RedirectResponse("/cabinet", status_code=303)
        response.set_cookie(COOKIE_NAME, make_session(login, SECRET_KEY), httponly=True)
        return response
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Неверный логин или пароль"},
        status_code=401,
    )


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/cabinet")
def cabinet(request: Request):
    if not check_session(request.cookies.get(COOKIE_NAME), SECRET_KEY):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="cabinet.html",
        context={"requests": get_requests()},
    )
