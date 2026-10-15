"""Numbers shown on the dashboard and the Gantt chart of one project."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .. import repositories as repo
from ..constants import SUMMARY_TASK_TYPE


def dashboard_context(db: Session, project_id: int, today: str) -> dict[str, Any]:
    project = repo.get_project(db, project_id)
    tasks = [t for t in repo.all_tasks(db, project_id) if t.task_type != SUMMARY_TASK_TYPE]
    updated = [t for t in tasks if t.updated_at]
    actual_progress = None if not updated else sum(float(t.actual_progress or 0) for t in updated) / len(updated)
    risk_total, risk_high, risks = repo.open_risk_summary(db, project_id)

    duration = 0
    elapsed = 0
    if project and project.start_date and project.end_date:
        start = date.fromisoformat(project.start_date)
        end = date.fromisoformat(project.end_date)
        duration = max(1, (end - start).days)
        report = date.fromisoformat(project.report_date or today)
        elapsed = max(0, min(100, (report - start).days / duration * 100))

    return {
        "tasks_total": len(tasks),
        "tasks_updated": len(updated),
        "completed": sum(1 for t in tasks if t.actual_status == "Hoàn thành"),
        "in_progress": sum(1 for t in tasks if t.actual_status == "Đang thi công"),
        "overdue": sum(1 for t in tasks if t.end_date and t.end_date < today and t.actual_status != "Hoàn thành"),
        "actual_progress": actual_progress,
        "risk_total": risk_total,
        "risk_high": risk_high,
        "cost": repo.cost_totals(db, project_id),
        "risks": risks,
        "upcoming": repo.upcoming_tasks(db, project_id, today),
        "groups": repo.task_groups(db, project_id),
        "diary_latest": repo.diary_entries(db, project_id, limit=3),
        "duration": duration,
        "elapsed": elapsed,
    }


def gantt_context(db: Session, project_id: int) -> dict[str, Any]:
    items = repo.tasks_for_gantt(db, project_id)
    project = repo.get_project(db, project_id)
    if not project or not project.start_date or not project.end_date:
        start = date.today()
        end = start + timedelta(days=30)
    else:
        start = date.fromisoformat(project.start_date)
        end = date.fromisoformat(project.end_date)
    span = max(1, (end - start).days)

    from . import control
    sched = control.schedule(db, project_id)
    baseline = control.active_baseline(db, project_id)
    base = control.baseline_dates(db, baseline)
    has_links = bool(sched["deps"]) and not sched["error"]

    def place(a: str | None, b: str | None) -> tuple[float, float]:
        try:
            s, e = date.fromisoformat(a), date.fromisoformat(b)
            left = max(0, min(100, (s - start).days / span * 100))
            return left, max(0.8, min(100 - left, ((e - s).days + 1) / span * 100))
        except Exception:
            return 0, 0

    bars = []
    for item in items:
        left, width = place(item.start_date, item.end_date)
        entry = {"item": item, "left": left, "width": width, "critical": False, "shift": 0,
                 "base_left": 0, "base_width": 0, "base_end": None, "slip": 0}
        r = sched["result"].get(item.id)
        if r is not None and has_links:
            entry["critical"] = r.critical
            entry["shift"] = r.shift
        b = base.get(item.id)
        if b is not None and b.start_date and b.end_date:
            entry["base_left"], entry["base_width"] = place(b.start_date, b.end_date)
            entry["base_end"] = b.end_date
            try:
                entry["slip"] = (date.fromisoformat(item.end_date) - date.fromisoformat(b.end_date)).days
            except Exception:
                pass
        bars.append(entry)

    months = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_start = max(cursor, start)
        month_end = min(next_month, end + timedelta(days=1))
        months.append({
            "label": cursor.strftime("%m/%Y"),
            "left": max(0, (month_start - start).days / span * 100),
            "width": max(0.8, (month_end - month_start).days / span * 100),
        })
        cursor = next_month
    deps = [{"p": d.predecessor_id, "s": d.successor_id, "t": d.dep_type} for d in sched["deps"]]
    today = date.today()
    today_left = (today - start).days / span * 100 if start <= today <= end else None
    return {"items": bars, "months": months, "start": start, "end": end, "deps": deps, "baseline": baseline,
            "has_links": has_links, "today_left": today_left}
