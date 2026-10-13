"""Overview, project settings, Gantt and reports of one project (/p/{project_id}/...). Excel import: imports.py."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import get_db
from ..models import Diary, Risk, SafetyLog, Task
from ..schemas import ProjectForm
from ..services import excel_export, stats
from ..web import flash, redirect, render

router = APIRouter()


@router.get("/", name="dashboard")
def dashboard(request: Request, project_id: int, db: Session = Depends(get_db)):
    return render(request, "dashboard.html", title="Tổng quan",
                  **stats.dashboard_context(db, project_id, date.today().isoformat()))


@router.get("/project", name="project_settings")
def project_settings(request: Request, project_id: int, db: Session = Depends(get_db)):
    item = repo.get_project(db, project_id)
    duration_days = None
    if item and item.start_date and item.end_date:
        try:
            duration_days = (date.fromisoformat(item.end_date) - date.fromisoformat(item.start_date)).days
        except ValueError:
            duration_days = None
    return render(request, "project.html", title="Thông tin dự án", item=item, duration_days=duration_days)


@router.post("/project", name="project_settings")
def project_settings_save(request: Request, project_id: int, form: Annotated[ProjectForm, Form()],
                          db: Session = Depends(get_db)):
    repo.update_project(db, project_id, form.model_dump())
    flash(request, "Đã lưu thông tin dự án.", "success")
    return redirect(request, "project_settings")


@router.get("/gantt", name="gantt")
def gantt(request: Request, project_id: int, db: Session = Depends(get_db)):
    return render(request, "gantt.html", title="Tiến độ Gantt", **stats.gantt_context(db, project_id))


@router.get("/reports", name="reports")
def reports(request: Request, project_id: int, db: Session = Depends(get_db)):
    return render(request, "reports.html", title="Báo cáo & xuất dữ liệu",
                  task_count=repo.count_rows(db, Task, project_id), risk_count=repo.count_rows(db, Risk, project_id),
                  cost=repo.cost_totals(db, project_id), diary_count=repo.count_rows(db, Diary, project_id),
                  hsse_count=repo.count_rows(db, SafetyLog, project_id), p=repo.get_project(db, project_id))


@router.get("/reports/export.xlsx", name="export_xlsx")
def export_xlsx(request: Request, project_id: int, db: Session = Depends(get_db)):
    content = excel_export.build_report(db, project_id)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Bao_cao_quan_ly_du_an_AZB.xlsx"'},
    )
