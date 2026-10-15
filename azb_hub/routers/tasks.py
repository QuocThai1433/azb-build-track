from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..constants import PRIORITIES, STATUSES
from ..db import get_db
from ..models import Task
from .deps import require
from ..schemas import TaskForm
from ..web import flash, or_404, redirect, render

router = APIRouter()


def _values(form: TaskForm) -> dict:
    """Map the posted form onto Task columns (plan % arrives as 0-100, stored as 0-1)."""
    actual_progress = max(0, min(100, form.actual_progress))
    touched = (form.actual_status != "Chưa cập nhật" or actual_progress > 0
               or form.actual_start_date or form.actual_end_date)
    return {
        "source_id": form.source_id, "category": form.category, "title": form.title.strip(),
        "task_type": form.task_type, "planned_days": form.planned_days,
        "start_date": form.start_date, "end_date": form.end_date,
        "plan_progress": form.plan_progress / 100, "plan_status": form.plan_status,
        "float_days": form.float_days, "notes": form.notes,
        "actual_progress": actual_progress, "actual_status": form.actual_status, "owner": form.owner,
        "actual_start_date": form.actual_start_date, "actual_end_date": form.actual_end_date,
        "updated_at": datetime.now().isoformat(timespec="seconds") if touched else None,
        "priority": form.priority if form.priority in PRIORITIES else "Trung bình",
    }


@router.get("/tasks", name="tasks_list")
def tasks_list(request: Request, project_id: int, db: Session = Depends(get_db), q: str = "", status: str = "",
               group: str = "", priority: str = "", overdue: str = ""):
    q, status, group, priority = q.strip(), status.strip(), group.strip(), priority.strip()
    overdue_only = overdue.strip() == "1"
    today = date.today().isoformat()
    return render(
        request, "tasks.html", title="Công việc & tiến độ",
        items=repo.list_tasks(db, project_id, q, status, group, priority, overdue_only, today),
        statuses=STATUSES, priorities=PRIORITIES, q=q, status=status, group=group, priority=priority,
        groups=repo.task_categories(db, project_id), overdue_only=overdue_only,
        overdue_count=repo.count_overdue_tasks(db, project_id, today),
        high_priority_count=repo.count_high_priority_tasks(db, project_id))


def _form_page(request: Request, title: str, item):
    return render(request, "task_form.html", title=title, item=item, statuses=STATUSES, priorities=PRIORITIES)


@router.get("/tasks/new", name="task_new")
def task_new(request: Request, project_id: int):
    return _form_page(request, "Thêm công việc", None)


@router.post("/tasks/new", name="task_new")
def task_create(request: Request, project_id: int, form: Annotated[TaskForm, Form()], db: Session = Depends(get_db)):
    values = _values(form)
    if not values["title"]:
        flash(request, "Vui lòng nhập tên công việc.", "error")
        return _form_page(request, "Thêm công việc", None)
    repo.create(db, Task, project_id, values)
    flash(request, "Đã thêm công việc mới.", "success")
    return redirect(request, "tasks_list")


@router.get("/tasks/{task_id}/edit", name="task_edit")
def task_edit(request: Request, project_id: int, task_id: int, db: Session = Depends(get_db)):
    return _form_page(request, "Cập nhật công việc", or_404(repo.get(db, Task, project_id, task_id)))


@router.post("/tasks/{task_id}/edit", name="task_edit")
def task_update(request: Request, project_id: int, task_id: int, form: Annotated[TaskForm, Form()],
                db: Session = Depends(get_db)):
    item = or_404(repo.get(db, Task, project_id, task_id))
    values = _values(form)
    if not values["title"]:
        flash(request, "Vui lòng nhập tên công việc.", "error")
        return _form_page(request, "Cập nhật công việc", item)
    repo.update(db, item, values)
    flash(request, "Đã cập nhật công việc và tiến độ thực tế.", "success")
    return redirect(request, "tasks_list")


@router.post("/tasks/{task_id}/delete", name="task_delete", dependencies=[Depends(require("record.delete"))])
def task_delete(request: Request, project_id: int, task_id: int, db: Session = Depends(get_db)):
    repo.remove(db, Task, project_id, task_id)
    flash(request, "Đã xóa công việc.", "success")
    return redirect(request, "tasks_list")
