"""Template engine, URLs, flash messages and the helpers every route shares.

Project pages live under /p/{project_id}/... . Templates keep calling url_for('tasks_list'): the
url_for below adds the current project's id by itself, so templates do not need to pass it.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from starlette.routing import NoMatchFound

from . import repositories as repo
from .constants import APP_VERSION
from .db import BASE_DIR, SessionLocal

SECRET_KEY = os.environ.get("PROJECT_MANAGER_SECRET", "azb-local-project-manager-change-me")


def fmt_money(value) -> str:
    try:
        return f"{float(value or 0):,.0f} ₫".replace(",", ".")
    except (TypeError, ValueError):
        return "0 ₫"


def fmt_compact_money(value) -> str:
    value = float(value or 0)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} tỷ ₫".replace(".", ",")
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} tr ₫".replace(".", ",")
    return fmt_money(value)


def _static_version() -> str:
    """Newest modification time of the static files. Appended to CSS/JS links as ?v=...,
    so the browser downloads a file again after it changes instead of using its cached copy."""
    files = [p for p in (BASE_DIR / "static").rglob("*") if p.is_file()]
    return str(int(max(p.stat().st_mtime for p in files))) if files else APP_VERSION


STATIC_VERSION = _static_version()


# ---- current project & URLs ------------------------------------------------------------------

def current_project_id(request: Request) -> int | None:
    """The project in the URL, else the last project the user opened (kept in the session)."""
    pid = request.path_params.get("project_id")
    if pid is None:
        pid = request.session.get("last_project")
    try:
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def path_for(request: Request, name: str, project_id: int | None = None, **params: Any) -> str:
    """URL path of a route. Routes under /p/{project_id} get the current project unless one is given."""
    pid = project_id if project_id is not None else current_project_id(request)
    if pid is not None:
        try:
            return str(request.app.url_path_for(name, project_id=pid, **params))
        except NoMatchFound:
            pass
    return str(request.app.url_path_for(name, **params))


@pass_context
def _url_for(context, name: str, **params: Any) -> str:
    request: Request = context["request"]
    pid = params.pop("project_id", None)
    if pid is None:
        pid = context.get("current_project_id")
    try:
        return path_for(request, name, project_id=pid, **params)
    except NoMatchFound:
        # A project page asked for while no project exists at all: send people to the project list.
        return str(request.app.url_path_for("projects_list"))


def _inject_globals(request: Request) -> dict[str, Any]:
    pid = current_project_id(request)
    with SessionLocal() as db:
        projects = repo.list_projects(db)
        if pid is None or repo.get_project(db, pid) is None:
            fallback = projects or repo.list_projects(db, include_archived=True)
            pid = fallback[0].id if fallback else None
        project = repo.get_project(db, pid) if pid is not None else None
    route = request.scope.get("route")
    return {"project": project, "current_project_id": pid, "projects": projects,
            "active_endpoint": getattr(route, "name", "") or "",
            "today": date.today().isoformat(), "app_version": APP_VERSION, "static_version": STATIC_VERSION}


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"), context_processors=[_inject_globals])
templates.env.filters["money"] = fmt_money
templates.env.filters["compact_money"] = fmt_compact_money
templates.env.globals["url_for"] = _url_for


# ---- flash messages --------------------------------------------------------------------------

def flash(request: Request, message: str, category: str = "info") -> None:
    flashes = list(request.session.get("_flashes", []))
    flashes.append([category, message])
    request.session["_flashes"] = flashes


@pass_context
def get_flashed_messages(context, with_categories: bool = False):
    request: Request = context["request"]
    flashes = request.session.pop("_flashes", [])
    return [(c, m) for c, m in flashes] if with_categories else [m for _, m in flashes]


templates.env.globals["get_flashed_messages"] = get_flashed_messages


# ---- responses -------------------------------------------------------------------------------

def render(request: Request, template: str, **context: Any):
    return templates.TemplateResponse(request, template, context)


def redirect(request: Request, route_name: str, **path_params: Any) -> RedirectResponse:
    """303 so the browser turns the POST into a GET on the target page."""
    return RedirectResponse(path_for(request, route_name, **path_params), status_code=303)


def or_404(obj):
    if obj is None:
        raise HTTPException(status_code=404)
    return obj
