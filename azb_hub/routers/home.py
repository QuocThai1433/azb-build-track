"""The home page (a public landing page for guests; after sign in, the project list) and the JSON search it calls while typing."""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..auth import ROLE_LABELS, can
from ..db import get_db
from ..services import home as home_service
from ..web import path_for, render

router = APIRouter()
RECENT_LIMIT = 4


def _with_urls(request: Request, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**c, "url": path_for(request, "dashboard", project_id=c["id"])} for c in cards]


@router.get("/", name="home")
def home(request: Request, db: Session = Depends(get_db), q: str = "", status: str = "", year: str = "",
         sort: str = "recent"):
    user = request.state.user
    if user is None:
        return render(request, "landing.html", title="Quản Lý Kế Hoạch Thi Công")
    cards = home_service.all_cards(db, user, home_service.today_iso())
    shown = home_service.filter_cards(cards, q, status, year, sort)
    by_id = {c["id"]: c for c in cards}
    recent_ids = [i for i in request.session.get("recent_projects", []) if isinstance(i, int)]
    recent = [by_id[i] for i in recent_ids if i in by_id][:RECENT_LIMIT]
    assigned_ids = repo.member_project_ids(db, user.id)
    staff = user.role == "nhan_vien"
    assigned = [] if staff else [c for c in cards if c["id"] in assigned_ids]    # for staff the whole list is theirs
    return render(request, "home.html", title="Trang chủ", cards=_with_urls(request, shown),
                  total_all=len(cards), recent=_with_urls(request, recent), assigned=_with_urls(request, assigned),
                  kpi=home_service.kpis(db, cards) if can(user, "project.view_all") else None,
                  q=q, status=status, year=year, sort=sort if sort in home_service.SORTS else "recent",
                  years=sorted({c["year"] for c in cards if c["year"]}, reverse=True),
                  status_labels=home_service.STATUS_LABELS, sorts=home_service.SORTS,
                  role_label=ROLE_LABELS.get(user.role, ""), is_staff=staff)


@router.get("/api/projects/search", name="projects_search")
def projects_search(request: Request, db: Session = Depends(get_db), q: str = "", status: str = "",
                    year: str = "", sort: str = "recent", limit: Annotated[int, Query(ge=1, le=100)] = 50):
    """Projects the signed-in user may open, filtered. Staff never get a project they are not assigned to."""
    cards = home_service.all_cards(db, request.state.user, home_service.today_iso())
    found = home_service.filter_cards(cards, q, status, year, sort)
    return {"total": len(found), "projects": _with_urls(request, found[:limit])}
