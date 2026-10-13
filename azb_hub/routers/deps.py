from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import get_db
from ..models import Project


def load_project(request: Request, project_id: int, db: Session = Depends(get_db)) -> Project:
    """Runs before every /p/{project_id}/... route: 404 for an unknown project, and remember it as the last one opened."""
    project = repo.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    if request.session.get("last_project") != project_id:
        request.session["last_project"] = project_id
    return project
