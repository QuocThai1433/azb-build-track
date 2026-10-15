"""The audit log page (admin and director): filter, page through, export to Excel. Read only."""
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit
from .. import repositories as repo
from ..audit import ACTIONS
from ..db import get_db
from ..models import AuditLog
from ..services import excel_export
from ..web import flash, redirect, render
from .deps import require

router = APIRouter(dependencies=[Depends(require("audit.view"))])
PAGE_SIZE = 50
ACTION_LABELS = {"create": "Thêm", "update": "Sửa", "delete": "Xóa", "login": "Đăng nhập", "logout": "Đăng xuất",
                 "login_failed": "Đăng nhập sai", "import": "Nhập Excel", "export": "Xuất Excel",
                 "approve": "Duyệt", "reject": "Từ chối", "denied": "Bị từ chối quyền"}


def _int(value: str) -> int | None:
    return int(value) if value.strip().isdigit() else None


def _filters(user_id: str, project_id: str, action: str, date_from: str, date_to: str) -> dict:
    action = action if action in ACTIONS else ""
    return {"user_id": _int(user_id), "project_id": _int(project_id), "action": action,
            "date_from": date_from.strip()[:10], "date_to": date_to.strip()[:10]}


@router.get("/audit-logs", name="audit_logs")
def audit_logs(request: Request, db: Session = Depends(get_db), user_id: str = "", project_id: str = "",
               action: str = "", date_from: str = "", date_to: str = "",
               page: Annotated[int, Query(ge=1)] = 1):
    f = _filters(user_id, project_id, action, date_from, date_to)
    total = repo.count_audit_logs(db, **f)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, pages)
    rows = repo.list_audit_logs(db, **f, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    query = {k: v for k, v in {"user_id": f["user_id"], "project_id": f["project_id"], "action": f["action"],
                               "date_from": f["date_from"], "date_to": f["date_to"]}.items() if v not in (None, "")}
    return render(request, "audit_logs.html", title="Nhật ký hoạt động", rows=rows, total=total, page=page,
                  pages=pages, f=f, query=query, users=repo.list_users(db),
                  projects=repo.list_projects(db, include_archived=True), actions=ACTIONS,
                  action_labels=ACTION_LABELS, project_names={p.id: p.name for p in
                                                              repo.list_projects(db, include_archived=True)})


@router.get("/audit-logs/export.xlsx", name="audit_logs_export")
def audit_logs_export(request: Request, db: Session = Depends(get_db), user_id: str = "", project_id: str = "",
                      action: str = "", date_from: str = "", date_to: str = ""):
    f = _filters(user_id, project_id, action, date_from, date_to)
    rows = repo.list_audit_logs(db, **f, limit=20000, offset=0)
    content = excel_export.build_audit_log(rows)
    audit.record(db, "export", "audit_logs", new={"rows": len(rows), **{k: v for k, v in f.items() if v}})
    stamp = date.today().strftime("%Y%m%d")
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Nhat_ky_hoat_dong_{stamp}.xlsx"'})


@router.post("/audit-logs/{log_id}/revert", name="audit_revert", dependencies=[Depends(require("audit.revert"))])
def audit_revert(request: Request, log_id: int, db: Session = Depends(get_db)):
    log = db.get(AuditLog, log_id)
    if log is None:
        raise HTTPException(status_code=404)
    error = repo.revert_update(db, log)
    if error:
        flash(request, error, "error")
    else:
        flash(request, "Đã hoàn tác thay đổi về giá trị trước.", "success")
    return redirect(request, "audit_logs")
