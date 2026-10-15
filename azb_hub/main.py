import asyncio
import os
from contextlib import asynccontextmanager

from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import audit
from .db import BASE_DIR, SessionLocal, run_migrations
from .models import User
from .routers import auth as auth_router
from .routers import audit as audit_router
from .routers import ai_plan, attachments as attachments_router, home, imports, logs, pages, projects, records, schedule, tasks, users
from .routers.deps import load_project
from .services import backup
from .services.seed import ensure_admin, seed_if_empty
from .slugs import ProjectConvertor
from .web import DEFAULT_SECRET, SECRET_KEY, flash


async def _auto_backup_loop() -> None:
    """Check once an hour; backup_if_due only writes a file when the newest automatic one is a day old."""
    while True:
        try:
            await asyncio.to_thread(backup.backup_if_due)
        except Exception as exc:                               # a failed backup must never stop the app
            print(f"CẢNH BÁO: sao lưu tự động lỗi: {exc}")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    with SessionLocal() as db:
        seed_if_empty(db)
        ensure_admin(db)
    if SECRET_KEY == DEFAULT_SECRET:
        print("CẢNH BÁO: đang dùng khóa phiên mặc định. Hãy đặt biến môi trường PROJECT_MANAGER_SECRET.")
    task = None if os.environ.get("AZB_AUTO_BACKUP", "1") == "0" else asyncio.create_task(_auto_backup_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="AZB Project Hub", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
PUBLIC_PREFIXES = ("/login", "/static/")
PUBLIC_PATHS = ("/", "/register")                             # exact paths open to guests: landing page, sign-up form
PASSWORD_PAGES = ("/account/password", "/logout")


@app.middleware("http")
async def sign_in_gate(request: Request, call_next):
    """Every request: find the signed-in user, tell the audit log who is acting, and send anonymous visitors to
    /login. Added before SessionMiddleware, so it runs inside it and can read request.session."""
    path = request.url.path
    user = None
    user_id = request.session.get("user_id")
    if user_id is not None:
        with SessionLocal() as db:
            found = db.get(User, user_id)
            if found is not None and found.is_active:
                user = found
            else:
                request.session.clear()                       # deleted or locked while signed in
    request.state.user = user
    client = request.client.host if request.client else None
    token = audit.set_actor(audit.Actor(user.id if user else None, user.username if user else None, client,
                                        request.headers.get("user-agent")))
    try:
        if user is None and path not in PUBLIC_PATHS and not path.startswith(PUBLIC_PREFIXES):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Bạn cần đăng nhập."}, status_code=401)
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
        if user is not None and user.must_change_password and not path.startswith(PASSWORD_PAGES + ("/static/",)):
            return RedirectResponse("/account/password", status_code=303)
        return await call_next(request)
    finally:
        audit.reset_actor(token)


@app.exception_handler(StarletteHTTPException)
async def forbidden_as_dialog(request: Request, exc: StarletteHTTPException):
    """A 403 on a page becomes a dialog in the middle of the screen: flash the message and go back to the page
    the person came from (or the home page). API calls and other errors keep the normal JSON/HTML answer."""
    browser = "text/html" in request.headers.get("accept", "")
    if exc.status_code != 403 or not browser or request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    flash(request, str(exc.detail), "denied")
    target = "/"
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        same_host = parts.netloc in ("", request.headers.get("host", ""))
        if same_host and parts.path and parts.path != request.url.path and not parts.path.startswith("//"):
            target = parts.path + (f"?{parts.query}" if parts.query else "")
    return RedirectResponse(target, status_code=303)


app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(audit_router.router)
app.include_router(home.router)
app.include_router(projects.router)
# Every page of a project lives under /<slug>/... ; the "project" convertor (slugs.py) turns the
# slug into project_id, and load_project returns 404 for an unknown one.
for module in (pages, imports, ai_plan, tasks, schedule, records, logs, attachments_router):
    app.include_router(module.router, prefix="/{project_id:project}", dependencies=[Depends(load_project)])


@app.api_route("/p/{project_id:int}", methods=["GET", "POST"], include_in_schema=False)
@app.api_route("/p/{project_id:int}/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def legacy_project_url(request: Request, project_id: int, rest: str = ""):
    """Old /p/<id>/... links and bookmarks keep working: send them to /<slug>/..."""
    target = f"/{ProjectConvertor().to_string(project_id)}/{rest}"
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(target, status_code=308)
