"""HSSE safety log and the site diary: one page each, with the entry form above the list."""
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import get_db
from ..models import Diary, SafetyLog
from ..schemas import DiaryForm, HsseForm
from ..web import flash, redirect, render
from .deps import require

router = APIRouter()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hsse_page(request: Request, db: Session, project_id: int):
    total_logs, high_logs = repo.safety_log_counts(db, project_id)
    return render(request, "hsse.html", title="An toàn HSSE", metrics=repo.hsse_metrics(db, project_id),
                  logs=repo.safety_logs(db, project_id, limit=100), total_logs=total_logs, high_logs=high_logs)


@router.get("/hsse", name="hsse")
def hsse(request: Request, project_id: int, db: Session = Depends(get_db)):
    return _hsse_page(request, db, project_id)


@router.post("/hsse", name="hsse")
def hsse_add(request: Request, project_id: int, form: Annotated[HsseForm, Form()], db: Session = Depends(get_db)):
    if not form.description.strip():
        flash(request, "Vui lòng nhập nội dung ghi nhận HSSE.", "error")
        return _hsse_page(request, db, project_id)
    repo.create(db, SafetyLog, project_id, {
        "log_date": form.log_date or date.today().isoformat(), "log_type": form.log_type,
        "description": form.description, "people_affected": int(form.people_affected),
        "severity": form.severity, "status": form.status, "reporter": form.reporter, "created_at": _now()})
    flash(request, "Đã lưu nhật ký HSSE.", "success")
    return redirect(request, "hsse")


@router.post("/hsse/{log_id}/delete", name="hsse_delete", dependencies=[Depends(require("record.delete"))])
def hsse_delete(request: Request, project_id: int, log_id: int, db: Session = Depends(get_db)):
    repo.remove(db, SafetyLog, project_id, log_id)
    flash(request, "Đã xóa nhật ký HSSE.", "success")
    return redirect(request, "hsse")


def _diary_page(request: Request, db: Session, project_id: int):
    return render(request, "diary.html", title="Nhật ký công trường", items=repo.diary_entries(db, project_id),
                  total=repo.count_rows(db, Diary, project_id))


@router.get("/diary", name="diary")
def diary(request: Request, project_id: int, db: Session = Depends(get_db)):
    return _diary_page(request, db, project_id)


@router.post("/diary", name="diary")
def diary_add(request: Request, project_id: int, form: Annotated[DiaryForm, Form()], db: Session = Depends(get_db)):
    work = form.completed_work.strip()
    if not work:
        flash(request, "Vui lòng nhập công việc đã thực hiện.", "error")
        return _diary_page(request, db, project_id)
    repo.create(db, Diary, project_id, {
        "log_date": form.log_date or date.today().isoformat(), "weather": form.weather,
        "worker_count": int(form.worker_count), "completed_work": work, "issues": form.issues,
        "reporter": form.reporter, "created_at": _now()})
    flash(request, "Đã lưu nhật ký công trường.", "success")
    return redirect(request, "diary")


@router.post("/diary/{log_id}/delete", name="diary_delete", dependencies=[Depends(require("record.delete"))])
def diary_delete(request: Request, project_id: int, log_id: int, db: Session = Depends(get_db)):
    repo.remove(db, Diary, project_id, log_id)
    flash(request, "Đã xóa nhật ký.", "success")
    return redirect(request, "diary")
