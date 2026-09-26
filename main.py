import os
import re
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import COOKIE_NAME, check_password, check_session, make_session
from db import (
    STATUSES,
    add_keyword,
    add_source,
    delete_keyword,
    delete_source,
    get_keywords,
    get_requests,
    get_sources,
    get_stats,
    insert_site_request,
    rename_keyword,
    rename_source,
    set_status,
)

load_dotenv()

CABINET_LOGIN = os.getenv("CABINET_LOGIN", "")
CABINET_PASSWORD_HASH = os.getenv("CABINET_PASSWORD_HASH", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Telegram отдаёт текст с markdown-разметкой: ссылки в виде [подпись](адрес), выделения
# звёздочками. В ленте это мешает читать, поэтому чистим при показе.
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_MARKS_RE = re.compile(r"[*_`~]")


def plain_text(text):
    """Текст без markdown-разметки: от ссылки остаётся только её подпись."""
    if not text:
        return ""
    return MARKDOWN_MARKS_RE.sub("", MARKDOWN_LINK_RE.sub(r"\1", text)).strip()


templates.env.filters["plain"] = plain_text


def authorized(request):
    """Пускать ли в кабинет: cookie должна быть подписана нашим секретом."""
    return check_session(request.cookies.get(COOKIE_NAME), SECRET_KEY)


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


@app.get("/cabinet/stats")
def cabinet_stats(request: Request):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={"stats": get_stats()},
    )


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/cabinet")
def cabinet(request: Request, status: str = "", q: str = ""):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="cabinet.html",
        context={
            "requests": get_requests(status=status, query=q),
            "statuses": STATUSES,
            "status": status,
            "query": q,
        },
    )


@app.post("/cabinet/status/{request_id}")
def cabinet_set_status(request: Request, request_id: int, status: str = Form()):
    """Переключатель статуса на карточке. Отвечает пустотой: страница не перезагружается."""
    if not authorized(request):
        return Response(status_code=403)
    set_status(request_id, status)
    return Response(status_code=204)


@app.get("/cabinet/settings")
def cabinet_settings(request: Request):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"sources": get_sources(), "keywords": get_keywords()},
    )


@app.post("/cabinet/settings/sources/add")
def settings_source_add(request: Request, name: str = Form()):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    if name.strip():
        add_source(name.strip())
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/cabinet/settings/sources/{source_id}/save")
def settings_source_save(request: Request, source_id: int, name: str = Form()):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    if name.strip():
        rename_source(source_id, name.strip())
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/cabinet/settings/sources/{source_id}/delete")
def settings_source_delete(request: Request, source_id: int):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    delete_source(source_id)
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/cabinet/settings/keywords/add")
def settings_keyword_add(request: Request, word: str = Form()):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    if word.strip():
        add_keyword(word.strip().lower())
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/cabinet/settings/keywords/{keyword_id}/save")
def settings_keyword_save(request: Request, keyword_id: int, word: str = Form()):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    if word.strip():
        rename_keyword(keyword_id, word.strip().lower())
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/cabinet/settings/keywords/{keyword_id}/delete")
def settings_keyword_delete(request: Request, keyword_id: int):
    if not authorized(request):
        return RedirectResponse("/login", status_code=303)
    delete_keyword(keyword_id)
    return RedirectResponse("/cabinet/settings", status_code=303)


@app.post("/zayavka")
def site_request(
    request: Request,
    name: str = Form(),
    contact: str = Form(),
    task: str = Form(),
):
    """Заявка с формы на визитке — в ту же таблицу, что и находки юзербота."""
    insert_site_request(author=name.strip(), contact=contact.strip(), text=task.strip())
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"year": datetime.now().year, "sent": True},
    )
