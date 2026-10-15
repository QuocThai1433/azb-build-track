"""Schedule control of one project: critical path, baseline variance, weighted progress, S-curve, EVM, alerts."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..constants import SUMMARY_TASK_TYPE
from ..models import (Baseline, BaselineTask, Cost, Holiday, ProgressSnapshot, Risk, Task, TaskDependency)
from . import scheduling


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def detail_tasks(db: Session, project_id: int) -> list[Task]:
    return [t for t in repo.all_tasks(db, project_id) if t.task_type != SUMMARY_TASK_TYPE]


def list_dependencies(db: Session, project_id: int) -> list[TaskDependency]:
    return list(db.scalars(select(TaskDependency).where(TaskDependency.project_id == project_id)
                           .order_by(TaskDependency.id)))


def list_holidays(db: Session, project_id: int) -> list[Holiday]:
    return list(db.scalars(select(Holiday).where(Holiday.project_id == project_id).order_by(Holiday.day)))


def list_baselines(db: Session, project_id: int) -> list[Baseline]:
    return list(db.scalars(select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.id.desc())))


def active_baseline(db: Session, project_id: int) -> Baseline | None:
    return db.scalar(select(Baseline).where(Baseline.project_id == project_id, Baseline.is_active.is_(True)))


def baseline_dates(db: Session, baseline: Baseline | None) -> dict[int, BaselineTask]:
    if baseline is None:
        return {}
    return {b.task_id: b for b in db.scalars(select(BaselineTask).where(BaselineTask.baseline_id == baseline.id))}


def build_calendar(db: Session, project_id: int, tasks: list[Task]) -> scheduling.WorkCalendar:
    project = repo.get_project(db, project_id)
    dates = [d for t in tasks for d in (_iso(t.start_date), _iso(t.end_date)) if d]
    if project:
        dates += [d for d in (_iso(project.start_date), _iso(project.end_date)) if d]
    first = (min(dates) if dates else date.today()) - timedelta(days=7)
    last = (max(dates) if dates else date.today()) + timedelta(days=730)      # room for tasks pushed far out
    return scheduling.WorkCalendar(
        first, last, scheduling.parse_work_days(project.work_days if project else None),
        [h.day for h in list_holidays(db, project_id)])


def schedule(db: Session, project_id: int) -> dict[str, Any]:
    """Critical-path result for the whole project plus the pieces the pages need."""
    tasks = detail_tasks(db, project_id)
    deps = list_dependencies(db, project_id)
    calendar = build_calendar(db, project_id, tasks)
    try:
        result = scheduling.compute(
            [{"id": t.id, "start_date": t.start_date, "end_date": t.end_date} for t in tasks],
            [(d.predecessor_id, d.successor_id, d.dep_type, d.lag_days) for d in deps], calendar)
        error = None
    except scheduling.CycleError as exc:
        result, error = {}, str(exc)
    return {"tasks": tasks, "deps": deps, "calendar": calendar, "result": result, "error": error,
            "finish": scheduling.project_finish(result)}


# ---- progress and EVM ------------------------------------------------------------------------

def _weight(t: Task) -> float:
    return max(0.0, float(t.weight if t.weight is not None else 1.0))


def planned_fraction(t: Task, day: date) -> float:
    s, e = _iso(t.start_date), _iso(t.end_date)
    if s is None or e is None:
        return 0.0
    if day < s:
        return 0.0
    if day >= e:
        return 1.0
    return ((day - s).days + 1) / ((e - s).days + 1)


def planned_progress_on(tasks: list[Task], day: date) -> float:
    total = sum(_weight(t) for t in tasks)
    if total <= 0:
        return 0.0
    return sum(_weight(t) * planned_fraction(t, day) for t in tasks) / total


def actual_progress(tasks: list[Task]) -> float:
    total = sum(_weight(t) for t in tasks)
    if total <= 0:
        return 0.0
    return sum(_weight(t) * min(100.0, max(0.0, float(t.actual_progress or 0))) / 100 for t in tasks) / total


def record_snapshot(db: Session, project_id: int, today: date | None = None) -> None:
    """Keep one planned/actual row per day. Written directly (no audit row): it is derived data."""
    today = today or date.today()
    tasks = detail_tasks(db, project_id)
    if not tasks:
        return
    row = db.scalar(select(ProgressSnapshot).where(ProgressSnapshot.project_id == project_id,
                                                   ProgressSnapshot.day == today.isoformat()))
    if row is None:
        row = ProgressSnapshot(project_id=project_id, day=today.isoformat())
        db.add(row)
    row.planned = planned_progress_on(tasks, today)
    row.actual = actual_progress(tasks)
    row.actual_cost = float(repo.cost_totals(db, project_id)["actual"] or 0)
    db.commit()


def evm(db: Session, project_id: int, tasks: list[Task], today: date) -> dict[str, Any]:
    project = repo.get_project(db, project_id)
    costs = repo.cost_totals(db, project_id)
    bac = float(costs["budget"] or 0) or float(getattr(project, "prelim_budget", 0) or 0)
    ac = float(costs["actual"] or 0)
    planned = planned_progress_on(tasks, today)
    actual = actual_progress(tasks)
    pv, ev = bac * planned, bac * actual
    spi = actual / planned if planned > 0 else None
    cpi = ev / ac if ac > 0 and bac > 0 else None

    start, end = _iso(project.start_date if project else None), _iso(project.end_date if project else None)
    forecast_end = None
    delay_days = None
    if start and end:
        elapsed = (today - start).days
        if actual >= 1:
            forecast_end = None
        elif elapsed > 0 and actual > 0:
            forecast_end = start + timedelta(days=round(elapsed / actual))
            delay_days = (forecast_end - end).days
    return {"bac": bac, "pv": pv, "ev": ev, "ac": ac, "planned": planned, "actual": actual, "spi": spi, "cpi": cpi,
            "eac": bac / cpi if cpi else None, "forecast_end": forecast_end, "delay_days": delay_days,
            "sv": ev - pv, "cv": ev - ac if ac > 0 else None}


def s_curve(db: Session, project_id: int, tasks: list[Task], today: date, forecast_end: date | None) -> dict[str, Any]:
    project = repo.get_project(db, project_id)
    dates = [d for t in tasks for d in (_iso(t.start_date), _iso(t.end_date)) if d]
    if project:
        dates += [d for d in (_iso(project.start_date), _iso(project.end_date)) if d]
    if not dates:
        return {"points": [], "start": None, "end": None}
    start, end = min(dates), max(dates + ([forecast_end] if forecast_end else []))
    span = max(1, (end - start).days)
    step = max(1, span // 40)
    snapshots = {s.day: s for s in db.scalars(select(ProgressSnapshot).where(ProgressSnapshot.project_id == project_id))}
    live = actual_progress(tasks)
    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=step)
    if days[-1] != end:
        days.append(end)
    points = []
    last_actual = None
    for d in days:
        key = d.isoformat()
        actual = None
        if d <= today:
            if key in snapshots:
                last_actual = snapshots[key].actual
            actual = last_actual
        points.append({"day": key, "planned": planned_progress_on(tasks, d), "actual": actual})
    return {"points": points, "start": start, "end": end, "today": today, "live": live, "span": span}


def alerts(db: Session, project_id: int, sched: dict[str, Any], metrics: dict[str, Any], today: date) -> list[dict]:
    out: list[dict] = []
    t_iso = today.isoformat()
    for t in sched["tasks"]:
        if t.end_date and t.end_date < t_iso and t.actual_status != "Hoàn thành":
            out.append({"level": "danger", "text": f"“{t.title}” quá hạn từ {t.end_date}."})
        elif t.start_date and t.start_date <= t_iso <= (t.end_date or t_iso) \
                and t.actual_status in ("Chưa cập nhật", "Chưa bắt đầu") and not t.actual_progress:
            out.append({"level": "warning", "text": f"“{t.title}” đến ngày bắt đầu ({t.start_date}) nhưng chưa có cập nhật."})
    for tid, s in sched["result"].items():
        if s.shift > 0:
            title = next((t.title for t in sched["tasks"] if t.id == tid), str(tid))
            out.append({"level": "warning", "text": f"“{title}” bị đẩy lùi {s.shift} ngày làm việc do công việc phía trước."})
    for r in db.scalars(select(Risk).where(Risk.project_id == project_id)):
        if r.due_date and r.due_date < t_iso and r.status not in ("Đã xử lý", "Chấp nhận rủi ro"):
            out.append({"level": "danger", "text": f"Rủi ro “{(r.description or '')[:60]}” quá hạn xử lý ({r.due_date})."})
    pending = db.scalar(select(func.count()).select_from(Cost).where(
        Cost.project_id == project_id, Cost.approval_status == "cho_duyet")) or 0
    if pending:
        out.append({"level": "info", "text": f"{pending} khoản chi phí đang chờ duyệt."})
    if metrics["spi"] is not None and metrics["spi"] < 0.9:
        out.append({"level": "danger", "text": f"SPI = {metrics['spi']:.2f}: tiến độ thực tế chậm hơn kế hoạch."})
    if metrics["cpi"] is not None and metrics["cpi"] < 0.9:
        out.append({"level": "warning", "text": f"CPI = {metrics['cpi']:.2f}: chi phí thực tế cao hơn giá trị đạt được."})
    rank = {"danger": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda a: rank[a["level"]])


def control_context(db: Session, project_id: int, today: date) -> dict[str, Any]:
    record_snapshot(db, project_id, today)
    sched = schedule(db, project_id)
    metrics = evm(db, project_id, sched["tasks"], today)
    baseline = active_baseline(db, project_id)
    base = baseline_dates(db, baseline)
    titles = {t.id: t for t in sched["tasks"]}
    critical = sorted((s for s in sched["result"].values() if s.critical and s.task_id in titles),
                      key=lambda s: s.es)
    variances = []
    for t in sched["tasks"]:
        b = base.get(t.id)
        if b and b.end_date and t.end_date:
            days = (date.fromisoformat(t.end_date) - date.fromisoformat(b.end_date)).days
            if days:
                variances.append({"task": t, "days": days, "baseline_end": b.end_date})
    variances.sort(key=lambda v: -abs(v["days"]))
    return {"sched": sched, "metrics": metrics, "baseline": baseline, "baselines": list_baselines(db, project_id),
            "holidays": list_holidays(db, project_id), "critical": critical, "titles": titles,
            "variances": variances, "curve": s_curve(db, project_id, sched["tasks"], today, metrics["forecast_end"]),
            "alerts": alerts(db, project_id, sched, metrics, today), "today": today}


def create_baseline(db: Session, project_id: int, name: str, user_name: str | None) -> Baseline:
    for old in list_baselines(db, project_id):
        old.is_active = False
    b = Baseline(project_id=project_id, name=name or f"Baseline {datetime.now():%d/%m/%Y %H:%M}",
                 created_at=datetime.now().isoformat(timespec="seconds"), created_by=user_name, is_active=True)
    db.add(b)
    db.flush()
    for t in detail_tasks(db, project_id):
        db.add(BaselineTask(baseline_id=b.id, task_id=t.id, start_date=t.start_date, end_date=t.end_date,
                            weight=_weight(t)))
    db.commit()
    return b
