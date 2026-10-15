"""Schedule control (/<project>/schedule): critical path, dependencies, baselines, working calendar, S-curve, EVM."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import get_db
from ..models import Baseline, Holiday, Task, TaskDependency
from ..services import control, scheduling
from ..web import flash, or_404, redirect, render
from .deps import require

router = APIRouter()

WEEKDAYS = [(0, "T2"), (1, "T3"), (2, "T4"), (3, "T5"), (4, "T6"), (5, "T7"), (6, "CN")]


@router.get("/schedule", name="schedule_control")
def schedule_page(request: Request, project_id: int, db: Session = Depends(get_db)):
    ctx = control.control_context(db, project_id, date.today())
    project = repo.get_project(db, project_id)
    work_days = set(scheduling.parse_work_days(project.work_days if project else None))
    return render(request, "schedule.html", title="Kiểm soát tiến độ", weekdays=WEEKDAYS, work_days=work_days,
                  dep_types=scheduling.DEP_TYPES, **ctx)


@router.post("/schedule/dependencies", name="dependency_add", dependencies=[Depends(require("record.write"))])
def dependency_add(request: Request, project_id: int, predecessor_id: Annotated[int, Form()],
                   successor_id: Annotated[int, Form()], dep_type: Annotated[str, Form()] = "FS",
                   lag_days: Annotated[int, Form()] = 0, db: Session = Depends(get_db)):
    pred = repo.get(db, Task, project_id, predecessor_id)
    succ = repo.get(db, Task, project_id, successor_id)
    if pred is None or succ is None:
        flash(request, "Không tìm thấy công việc đã chọn.", "error")
    elif dep_type not in scheduling.DEP_TYPES:
        flash(request, "Loại phụ thuộc không hợp lệ.", "error")
    elif any(d.predecessor_id == predecessor_id and d.successor_id == successor_id
             for d in control.list_dependencies(db, project_id)):
        flash(request, "Phụ thuộc này đã tồn tại.", "error")
    elif scheduling.would_cycle([(d.predecessor_id, d.successor_id) for d in control.list_dependencies(db, project_id)],
                                predecessor_id, successor_id):
        flash(request, "Không thêm được: phụ thuộc này tạo vòng lặp giữa các công việc.", "error")
    else:
        repo.create(db, TaskDependency, project_id, {
            "predecessor_id": predecessor_id, "successor_id": successor_id, "dep_type": dep_type,
            "lag_days": max(-365, min(365, lag_days))})
        flash(request, "Đã thêm phụ thuộc giữa hai công việc.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/dependencies/{dep_id}/delete", name="dependency_delete",
             dependencies=[Depends(require("record.write"))])
def dependency_delete(request: Request, project_id: int, dep_id: int, db: Session = Depends(get_db)):
    repo.remove(db, TaskDependency, project_id, dep_id)
    flash(request, "Đã xóa phụ thuộc.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/baselines", name="baseline_create", dependencies=[Depends(require("project.edit"))])
def baseline_create(request: Request, project_id: int, name: Annotated[str, Form()] = "",
                    db: Session = Depends(get_db)):
    user = request.state.user
    b = control.create_baseline(db, project_id, name.strip(), user.username if user else None)
    from .. import audit
    audit.record(db, "create", "baselines", b.id, project_id, new={"name": b.name})
    flash(request, f"Đã chốt baseline “{b.name}”. Kế hoạch gốc được lưu để so sánh.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/baselines/{baseline_id}/activate", name="baseline_activate",
             dependencies=[Depends(require("project.edit"))])
def baseline_activate(request: Request, project_id: int, baseline_id: int, db: Session = Depends(get_db)):
    target = or_404(repo.get(db, Baseline, project_id, baseline_id))
    for b in control.list_baselines(db, project_id):
        b.is_active = b.id == target.id
    db.commit()
    flash(request, f"Đang so sánh với baseline “{target.name}”.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/baselines/{baseline_id}/delete", name="baseline_delete",
             dependencies=[Depends(require("record.delete"))])
def baseline_delete(request: Request, project_id: int, baseline_id: int, db: Session = Depends(get_db)):
    repo.remove(db, Baseline, project_id, baseline_id)
    flash(request, "Đã xóa baseline.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/calendar", name="calendar_save", dependencies=[Depends(require("project.edit"))])
def calendar_save(request: Request, project_id: int, work_days: Annotated[list[int], Form()] = (),
                  db: Session = Depends(get_db)):
    days = sorted({d for d in work_days if 0 <= d <= 6})
    if not days:
        flash(request, "Cần chọn ít nhất một ngày làm việc trong tuần.", "error")
    else:
        repo.update_project(db, project_id, {"work_days": ",".join(str(d) for d in days)})
        flash(request, "Đã lưu lịch làm việc.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/holidays", name="holiday_add", dependencies=[Depends(require("project.edit"))])
def holiday_add(request: Request, project_id: int, day: Annotated[str, Form()],
                end_day: Annotated[str, Form()] = "", name: Annotated[str, Form()] = "",
                db: Session = Depends(get_db)):
    try:
        first = date.fromisoformat(day)
        last = date.fromisoformat(end_day) if end_day else first
    except ValueError:
        flash(request, "Ngày nghỉ không hợp lệ.", "error")
        return redirect(request, "schedule_control")
    if last < first or (last - first).days > 60:
        flash(request, "Khoảng nghỉ không hợp lệ (tối đa 60 ngày liên tiếp).", "error")
        return redirect(request, "schedule_control")
    have = {h.day for h in control.list_holidays(db, project_id)}
    added = 0
    for offset in range((last - first).days + 1):
        d = date.fromordinal(first.toordinal() + offset).isoformat()
        if d not in have:
            repo.create(db, Holiday, project_id, {"day": d, "name": name.strip()})
            added += 1
    flash(request, f"Đã thêm {added} ngày nghỉ.", "success")
    return redirect(request, "schedule_control")


@router.post("/schedule/holidays/{holiday_id}/delete", name="holiday_delete",
             dependencies=[Depends(require("project.edit"))])
def holiday_delete(request: Request, project_id: int, holiday_id: int, db: Session = Depends(get_db)):
    repo.remove(db, Holiday, project_id, holiday_id)
    flash(request, "Đã xóa ngày nghỉ.", "success")
    return redirect(request, "schedule_control")
