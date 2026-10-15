from contextlib import asynccontextmanager

from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import audit
from .db import BASE_DIR, SessionLocal, run_migrations
from .models import User
from .routers import auth as auth_router
from .routers import audit as audit_router
from .routers import ai_plan, home, imports, logs, pages, projects, records, tasks, users
from .routers.deps import load_project
from .services.seed import ensure_admin, seed_if_empty
from .slugs import ProjectConvertor
from .web import DEFAULT_SECRET, SECRET_KEY


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    with SessionLocal() as db:
        seed_if_empty(db)
        ensure_admin(db)
    if SECRET_KEY == DEFAULT_SECRET:
        print("CẢNH BÁO: đang dùng khóa phiên mặc định. Hãy đặt biến môi trường PROJECT_MANAGER_SECRET.")
    yield


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


app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(audit_router.router)
app.include_router(home.router)
app.include_router(projects.router)
# Every page of a project lives under /<slug>/... ; the "project" convertor (slugs.py) turns the
# slug into project_id, and load_project returns 404 for an unknown one.
for module in (pages, imports, ai_plan, tasks, records, logs):
    app.include_router(module.router, prefix="/{project_id:project}", dependencies=[Depends(load_project)])


@app.api_route("/p/{project_id:int}", methods=["GET", "POST"], include_in_schema=False)
@app.api_route("/p/{project_id:int}/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def legacy_project_url(request: Request, project_id: int, rest: str = ""):
    """Old /p/<id>/... links and bookmarks keep working: send them to /<slug>/..."""
    target = f"/{ProjectConvertor().to_string(project_id)}/{rest}"
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(target, status_code=308)
