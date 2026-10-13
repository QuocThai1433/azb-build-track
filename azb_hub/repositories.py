"""Every database query lives here. Routes and services never build SQL themselves.

Every query on project data takes ``project_id`` and filters on it, so one project never sees
another project's rows. Write helpers commit before returning, so a route that redirects
afterwards never races its own commit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Text, and_, case, cast, delete, func, or_, select
from sqlalchemy.orm import Session

from . import slugs
from .constants import CLOSED_RISK_STATUSES, SUMMARY_TASK_TYPE
from .models import (Base, Cost, Diary, HsseMetric, ImportAlias, Method, Project, Resource, Risk, SafetyLog,
                     Task)

M = TypeVar("M", bound=Base)

ACTIVE = "active"
ARCHIVED = "archived"


# ---- generic helpers -------------------------------------------------------------------------

def get(db: Session, model: type[M], project_id: int, record_id: int) -> M | None:
    """A record by id, but only if it belongs to the given project."""
    obj = db.get(model, record_id)
    return obj if obj is not None and obj.project_id == project_id else None


def create(db: Session, model: type[M], project_id: int, values: dict[str, Any]) -> M:
    obj = model(project_id=project_id, **values)
    db.add(obj)
    db.commit()
    return obj


def update(db: Session, obj: Base, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(obj, key, value)
    db.commit()


def remove(db: Session, model: type[Base], project_id: int, record_id: int) -> None:
    db.execute(delete(model).where(model.id == record_id, model.project_id == project_id))
    db.commit()


def count_rows(db: Session, model: type[Base], project_id: int) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0


def to_dict(obj: Base) -> dict[str, Any]:
    return {column.key: getattr(obj, column.key) for column in obj.__table__.columns}


def _like(column, text: str):
    return column.like(f"%{text}%")


# ---- projects --------------------------------------------------------------------------------

def get_project(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def list_projects(db: Session, include_archived: bool = False) -> list[Project]:
    stmt = select(Project).order_by(Project.id)
    if not include_archived:
        stmt = stmt.where(Project.status == ACTIVE)
    return list(db.scalars(stmt))


def first_active_project_id(db: Session) -> int | None:
    return db.scalar(select(Project.id).where(Project.status == ACTIVE).order_by(Project.id).limit(1))


def new_project(values: dict[str, Any]) -> Project:
    """An unsaved Project. The caller adds it to a session and commits, possibly with other rows."""
    return Project(status=ACTIVE, created_at=datetime.now().isoformat(timespec="seconds"), **values)


def update_project(db: Session, project_id: int, values: dict[str, Any]) -> None:
    project = db.get(Project, project_id)
    if project is not None:
        update(db, project, values)


def set_project_status(db: Session, project_id: int, status: str) -> None:
    update_project(db, project_id, {"status": status})


PROJECT_DATA = ((Task, "tasks"), (Cost, "costs"), (Risk, "risks"), (Resource, "resources"), (Method, "methods"),
                (HsseMetric, "hsse_metrics"), (SafetyLog, "safety_logs"), (Diary, "diary"))


def data_counts_by_project(db: Session) -> dict[int, dict[str, int]]:
    """{project_id: {"tasks": 85, "costs": 63, ...}} for every project that has rows."""
    result: dict[int, dict[str, int]] = {}
    for model, key in PROJECT_DATA:
        for pid, n in db.execute(select(model.project_id, func.count()).group_by(model.project_id)):
            result.setdefault(pid, {})[key] = n
    return result


def delete_project(db: Session, project_id: int) -> None:
    """Delete a project. The database removes its rows in every data table (ON DELETE CASCADE)."""
    db.execute(delete(Project).where(Project.id == project_id))
    db.commit()
    slugs.clear_cache()


# ---- import aliases (choices remembered from the import preview) -----------------------------

def load_aliases(db: Session) -> dict[tuple[str, str], dict[str, str]]:
    """{("column", "tasks"): {normalised header: field or ""}, ("sheet", "costs"): {normalised sheet: ""}}"""
    result: dict[tuple[str, str], dict[str, str]] = {}
    for a in db.scalars(select(ImportAlias)):
        result.setdefault((a.kind, a.entity), {})[a.text_norm] = a.field or ""
    return result


def list_aliases(db: Session) -> list[ImportAlias]:
    return list(db.scalars(select(ImportAlias).order_by(ImportAlias.entity, ImportAlias.kind, ImportAlias.id)))


def save_alias(db: Session, kind: str, entity: str, text_norm: str, text_shown: str, field: str) -> None:
    """Insert or update one alias. The caller commits."""
    if not text_norm:
        return
    row = db.scalar(select(ImportAlias).where(ImportAlias.kind == kind, ImportAlias.entity == entity,
                                              ImportAlias.text_norm == text_norm))
    if row is None:
        db.add(ImportAlias(kind=kind, entity=entity, text_norm=text_norm, text_shown=text_shown, field=field,
                           created_at=datetime.now().isoformat(timespec="seconds")))
    else:
        row.field = field
        row.text_shown = text_shown


def delete_alias(db: Session, alias_id: int) -> None:
    db.execute(delete(ImportAlias).where(ImportAlias.id == alias_id))
    db.commit()


# ---- tasks -----------------------------------------------------------------------------------

_PRIORITY_RANK = case(
    {"Khẩn cấp": 0, "Cao": 1, "Trung bình": 2},
    value=func.coalesce(Task.priority, "Trung bình"),
    else_=3,
)


def list_tasks(db: Session, project_id: int, q: str = "", status: str = "", group: str = "", priority: str = "",
               overdue_only: bool = False, today: str = "") -> list[Task]:
    stmt = select(Task).where(Task.project_id == project_id)
    if q:
        stmt = stmt.where(or_(_like(Task.title, q), _like(Task.category, q),
                              _like(cast(Task.source_id, Text), q), _like(Task.owner, q)))
    if status:
        stmt = stmt.where(Task.actual_status == status)
    if group:
        stmt = stmt.where(Task.category == group)
    if priority:
        stmt = stmt.where(func.coalesce(Task.priority, "Trung bình") == priority)
    if overdue_only:
        stmt = stmt.where(Task.end_date.is_not(None), Task.end_date < today, Task.actual_status != "Hoàn thành")
    stmt = stmt.order_by(_PRIORITY_RANK, Task.source_id, Task.id)
    return list(db.scalars(stmt))


def task_categories(db: Session, project_id: int) -> list[str]:
    stmt = (select(Task.category).where(Task.project_id == project_id, Task.category.is_not(None), Task.category != "")
            .distinct().order_by(Task.category))
    return list(db.scalars(stmt))


def count_overdue_tasks(db: Session, project_id: int, today: str) -> int:
    stmt = select(func.count()).select_from(Task).where(
        Task.project_id == project_id, Task.task_type != SUMMARY_TASK_TYPE, Task.end_date.is_not(None),
        Task.end_date < today, Task.actual_status != "Hoàn thành")
    return db.scalar(stmt) or 0


def count_high_priority_tasks(db: Session, project_id: int) -> int:
    stmt = select(func.count()).select_from(Task).where(
        Task.project_id == project_id, Task.task_type != SUMMARY_TASK_TYPE,
        Task.priority.in_(["Khẩn cấp", "Cao"]), Task.actual_status != "Hoàn thành")
    return db.scalar(stmt) or 0


def all_tasks(db: Session, project_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.project_id == project_id)))


def upcoming_tasks(db: Session, project_id: int, today: str, limit: int = 5) -> list[Task]:
    stmt = (select(Task).where(Task.project_id == project_id, Task.task_type != SUMMARY_TASK_TYPE, Task.end_date >= today)
            .order_by(Task.end_date).limit(limit))
    return list(db.scalars(stmt))


def task_groups(db: Session, project_id: int, limit: int = 6) -> list[dict[str, Any]]:
    count = func.count().label("count")
    stmt = (select(Task.category, count, func.avg(Task.plan_progress).label("progress"))
            .where(Task.project_id == project_id, Task.task_type != SUMMARY_TASK_TYPE)
            .group_by(Task.category).order_by(count.desc()).limit(limit))
    return [{"category": r.category, "count": r.count, "progress": r.progress} for r in db.execute(stmt)]


def tasks_for_gantt(db: Session, project_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.start_date, Task.source_id)))


def tasks_for_export(db: Session, project_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.source_id)))


# ---- resources / costs / risks / methods -----------------------------------------------------

def list_resources(db: Session, project_id: int, q: str = "", resource_type: str = "") -> list[Resource]:
    stmt = select(Resource).where(Resource.project_id == project_id)
    if q:
        stmt = stmt.where(or_(_like(Resource.name, q), _like(Resource.group_name, q), _like(Resource.notes, q)))
    if resource_type:
        stmt = stmt.where(Resource.resource_type == resource_type)
    return list(db.scalars(stmt.order_by(Resource.resource_type, Resource.name)))


def resource_types(db: Session, project_id: int) -> list[str]:
    stmt = (select(Resource.resource_type).where(Resource.project_id == project_id, Resource.resource_type != "")
            .distinct().order_by(Resource.resource_type))
    return [t for t in db.scalars(stmt) if t is not None]


def resources_for_export(db: Session, project_id: int) -> list[Resource]:
    return list(db.scalars(select(Resource).where(Resource.project_id == project_id)
                           .order_by(Resource.resource_type, Resource.name)))


def list_costs(db: Session, project_id: int, q: str = "") -> list[Cost]:
    stmt = select(Cost).where(Cost.project_id == project_id)
    if q:
        stmt = stmt.where(or_(_like(Cost.name, q), _like(Cost.notes, q)))
    return list(db.scalars(stmt.order_by(Cost.budget_amount.desc())))


def cost_totals(db: Session, project_id: int) -> dict[str, float]:
    row = db.execute(select(func.coalesce(func.sum(Cost.budget_amount), 0).label("budget"),
                            func.coalesce(func.sum(Cost.actual_amount), 0).label("actual"))
                     .where(Cost.project_id == project_id)).one()
    return {"budget": row.budget, "actual": row.actual}


_SEVERITY_RANK = case({"Cao": 1, "Trung bình": 2}, value=Risk.severity, else_=3)
_OPEN_RISK = Risk.status.not_in(CLOSED_RISK_STATUSES)


def list_risks(db: Session, project_id: int, q: str = "", severity: str = "", status: str = "") -> list[Risk]:
    stmt = select(Risk).where(Risk.project_id == project_id)
    if q:
        stmt = stmt.where(or_(_like(Risk.description, q), _like(Risk.recommendation, q), _like(Risk.owner, q)))
    if severity:
        stmt = stmt.where(Risk.severity == severity)
    if status:
        stmt = stmt.where(Risk.status == status)
    return list(db.scalars(stmt.order_by(_SEVERITY_RANK, Risk.id)))


def risk_counts(db: Session, project_id: int) -> dict[str, int]:
    row = db.execute(select(
        func.coalesce(func.sum(case((and_(Risk.severity == "Cao", _OPEN_RISK), 1), else_=0)), 0).label("high"),
        func.coalesce(func.sum(case((Risk.status == "Đang xử lý", 1), else_=0)), 0).label("doing"),
        func.count().label("total")).where(Risk.project_id == project_id)).one()
    return {"high": row.high, "doing": row.doing, "total": row.total}


def open_risk_summary(db: Session, project_id: int, limit: int = 5) -> tuple[int, int, list[Risk]]:
    scope = and_(Risk.project_id == project_id, _OPEN_RISK)
    total = db.scalar(select(func.count()).select_from(Risk).where(scope)) or 0
    high = db.scalar(select(func.count()).select_from(Risk).where(scope, Risk.severity == "Cao")) or 0
    top = list(db.scalars(select(Risk).where(scope).order_by(_SEVERITY_RANK, Risk.id).limit(limit)))
    return total, high, top


def risks_for_export(db: Session, project_id: int) -> list[Risk]:
    return list(db.scalars(select(Risk).where(Risk.project_id == project_id).order_by(Risk.severity, Risk.id)))


def list_methods(db: Session, project_id: int, q: str = "") -> list[Method]:
    stmt = select(Method).where(Method.project_id == project_id)
    if q:
        stmt = stmt.where(or_(_like(Method.name, q), _like(Method.specification, q)))
    return list(db.scalars(stmt.order_by(Method.id)))


def methods_for_export(db: Session, project_id: int) -> list[Method]:
    return list(db.scalars(select(Method).where(Method.project_id == project_id).order_by(Method.id)))


# ---- HSSE / diary ----------------------------------------------------------------------------

def hsse_metrics(db: Session, project_id: int) -> list[HsseMetric]:
    return list(db.scalars(select(HsseMetric).where(HsseMetric.project_id == project_id).order_by(HsseMetric.id)))


def safety_logs(db: Session, project_id: int, limit: int | None = 100) -> list[SafetyLog]:
    stmt = (select(SafetyLog).where(SafetyLog.project_id == project_id)
            .order_by(SafetyLog.log_date.desc(), SafetyLog.id.desc()))
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def safety_log_counts(db: Session, project_id: int) -> tuple[int, int]:
    total = count_rows(db, SafetyLog, project_id)
    high = db.scalar(select(func.count()).select_from(SafetyLog).where(
        SafetyLog.project_id == project_id, SafetyLog.severity == "Cao", SafetyLog.status != "Đã đóng")) or 0
    return total, high


def diary_entries(db: Session, project_id: int, limit: int | None = None) -> list[Diary]:
    stmt = select(Diary).where(Diary.project_id == project_id).order_by(Diary.log_date.desc(), Diary.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))
