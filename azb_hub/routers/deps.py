from typing import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import audit, auth
from .. import repositories as repo
from ..db import get_db
from ..models import Project, User


def get_current_user(request: Request) -> User:
    """The signed-in user. The middleware in main.py has already redirected anonymous visitors to /login;
    this is the second line of defence for any route that slips through."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Bạn cần đăng nhập.")
    return user


def _deny(request: Request, db: Session, user: User, what: str, project_id: int | None = None) -> HTTPException:
    audit.record(db, "denied", entity_type=request.url.path[:120], project_id=project_id,
                 new={"method": request.method, "need": what})
    return HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này.")


def require(action: str) -> Callable:
    """Dependency factory: ``Depends(require("record.delete"))`` answers 403 unless the role may do that."""
    def check(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not auth.can(user, action):
            raise _deny(request, db, user, action, request.path_params.get("project_id"))
        return user
    return check


def load_project(request: Request, project_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> Project:
    """Runs before every /<slug>/... route: 404 for an unknown project, 403 for a staff member who is not
    assigned to it, and remember it as the last one opened."""
    project = repo.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    if not auth.can(user, "project.view_all") and not repo.is_member(db, user.id, project_id):
        raise _deny(request, db, user, "project.member", project_id)
    if request.session.get("last_project") != project_id:
        request.session["last_project"] = project_id
    recent = request.session.get("recent_projects", [])
    if not recent or recent[0] != project_id:
        request.session["recent_projects"] = ([project_id] + [i for i in recent if i != project_id])[:5]
    return project
