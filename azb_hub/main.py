from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import BASE_DIR, SessionLocal, run_migrations
from .routers import imports, logs, pages, projects, records, tasks
from .routers.deps import load_project
from .slugs import ProjectConvertor
from .services.seed import seed_if_empty
from .web import SECRET_KEY


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    with SessionLocal() as db:
        seed_if_empty(db)
    yield


app = FastAPI(title="AZB Project Hub", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(projects.router)
# Every page of a project lives under /<slug>/... ; the "project" convertor (slugs.py) turns the
# slug into project_id, and load_project returns 404 for an unknown one.
for module in (pages, imports, tasks, records, logs):
    app.include_router(module.router, prefix="/{project_id:project}", dependencies=[Depends(load_project)])


@app.api_route("/p/{project_id:int}", methods=["GET", "POST"], include_in_schema=False)
@app.api_route("/p/{project_id:int}/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def legacy_project_url(request: Request, project_id: int, rest: str = ""):
    """Old /p/<id>/... links and bookmarks keep working: send them to /<slug>/..."""
    target = f"/{ProjectConvertor().to_string(project_id)}/{rest}"
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(target, status_code=308)
