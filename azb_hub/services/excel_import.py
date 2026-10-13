"""Write an ImportPlan (see excel_mapping) to the database.

Two ways to import:
* import_as_new_project: the file becomes a new project; existing projects do not change.
* import_into_project: the file updates one project. What people entered in the app (actual progress,
  actual cost, risk owner...) is kept for rows that match: by WBS code, or by name when the file has none.

Rules for an update (decided by the user):
* a sheet the file does not have            -> that data stays as it is;
* a column the file does not have           -> the old value of that field stays on matched rows;
* a column that exists but a cell is empty  -> the field becomes empty (the plan follows the file).
Each import runs in one transaction: a failure leaves all data untouched.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..models import Cost, HsseMetric, Method, Project, Resource, Risk, Task
from .excel_mapping import EntityPlan, ImportPlan, norm


class ImportFormatError(ValueError):
    """The file cannot be imported. Nothing was changed."""


TASK_PLAN_DEFAULTS: dict[str, Any] = {
    "source_id": None, "category": "", "title": "", "task_type": "Chi tiết", "planned_days": 0.0,
    "start_date": None, "end_date": None, "duration_calculated": 0.0, "schedule_check": "",
    "plan_progress": 0.0, "plan_status": "", "tet_flag": "", "float_days": 0.0, "notes": ""}
TASK_USER_FIELDS = ("actual_progress", "actual_status", "owner", "actual_start_date", "actual_end_date",
                    "updated_at", "priority")
RISK_PLAN_DEFAULTS: dict[str, Any] = {
    "source_id": None, "category": "", "description": "", "basis": "", "severity": "Trung bình", "recommendation": ""}
COST_PLAN_DEFAULTS: dict[str, Any] = {
    "name": "", "category": "Chi phí Prelim", "unit": "", "quantity": 0.0, "unit_price": 0.0,
    "budget_amount": 0.0, "notes": ""}
RESOURCE_DEFAULTS: dict[str, Any] = {
    "name": "", "resource_type": "Nhân sự", "group_name": "", "quantity": 0.0, "duration_months": 0.0,
    "start_date": None, "end_date": None, "unit": "", "cost": 0.0, "notes": ""}
METHOD_DEFAULTS: dict[str, Any] = {"name": "", "unit": "", "quantity": 0.0, "specification": "", "schedule": "", "source": ""}
HSSE_DEFAULTS: dict[str, Any] = {"name": "", "value": 0.0, "unit": "", "notes": ""}


def _pick(row: dict[str, Any], key: str, default: Any) -> Any:
    value = row.get(key)
    return default if value is None else value


def _plain(obj: Any, keys) -> dict[str, Any]:
    return {k: getattr(obj, k) for k in keys}


def _merge_plan_fields(row: dict[str, Any], mapped: set[str], old: dict[str, Any] | None,
                       defaults: dict[str, Any]) -> dict[str, Any]:
    """File value for a mapped column, the old value for an unmapped column, else the default."""
    values: dict[str, Any] = {}
    for key, default in defaults.items():
        if key in mapped:
            values[key] = _pick(row, key, default)
        elif old is not None and old.get(key) is not None:
            values[key] = old[key]
        else:
            values[key] = default
    return values


# ---- entities --------------------------------------------------------------------------------

def _apply_tasks(db: Session, project_id: int, ep: EntityPlan, stats: dict[str, int]) -> int:
    old_rows = list(db.scalars(select(Task).where(Task.project_id == project_id)))
    snapshot = {t.id: _plain(t, list(TASK_PLAN_DEFAULTS) + list(TASK_USER_FIELDS)) for t in old_rows}
    by_id = {t.source_id: snapshot[t.id] for t in old_rows if t.source_id is not None}
    by_title: dict[str, dict[str, Any]] = {}
    for t in old_rows:
        by_title.setdefault(norm(t.title), snapshot[t.id])

    db.execute(delete(Task).where(Task.project_id == project_id))
    for row in ep.rows:
        old = None
        if row.get("source_id") is not None:
            old = by_id.get(row["source_id"])
            if old is not None:
                stats["matched_id"] += 1
        else:
            old = by_title.get(norm(row.get("title")))
            if old is not None:
                stats["matched_title"] += 1
        values = _merge_plan_fields(row, ep.mapped_fields, old, TASK_PLAN_DEFAULTS)
        if not values["task_type"]:
            values["task_type"] = "Chi tiết"
        user = {k: old[k] for k in TASK_USER_FIELDS} if old else {}
        db.add(Task(project_id=project_id, **values,
                    actual_progress=user.get("actual_progress") or 0,
                    actual_status=user.get("actual_status") or "Chưa cập nhật",
                    owner=user.get("owner") or "",
                    actual_start_date=user.get("actual_start_date"),
                    actual_end_date=user.get("actual_end_date"),
                    updated_at=user.get("updated_at"),
                    priority=user.get("priority") or "Trung bình"))
    return len(ep.rows)


def _apply_risks(db: Session, project_id: int, ep: EntityPlan) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    old_rows = list(db.scalars(select(Risk).where(Risk.project_id == project_id)))
    keys = list(RISK_PLAN_DEFAULTS) + ["owner", "due_date", "status", "created_at"]
    snapshot = [_plain(r, keys) for r in old_rows]
    by_id = {s["source_id"]: s for s in snapshot if s["source_id"] is not None}
    by_text: dict[str, dict[str, Any]] = {}
    for s in snapshot:
        by_text.setdefault(norm(s["description"]), s)

    db.execute(delete(Risk).where(Risk.project_id == project_id))
    for row in ep.rows:
        old = by_id.get(row["source_id"]) if row.get("source_id") is not None else by_text.get(norm(row.get("description")))
        values = _merge_plan_fields(row, ep.mapped_fields, old, RISK_PLAN_DEFAULTS)
        owner = _pick(row, "owner", None) if "owner" in ep.mapped_fields else None
        due = _pick(row, "due_date", None) if "due_date" in ep.mapped_fields else None
        db.add(Risk(project_id=project_id, **values,
                    owner=owner or (old or {}).get("owner") or "",
                    due_date=due or (old or {}).get("due_date"),
                    status=(old or {}).get("status") or "Chưa xử lý",
                    created_at=(old or {}).get("created_at") or now))
    return len(ep.rows)


def _apply_costs(db: Session, project_id: int, ep: EntityPlan) -> int:
    old_rows = list(db.scalars(select(Cost).where(Cost.project_id == project_id)))
    keys = list(COST_PLAN_DEFAULTS) + ["actual_amount"]
    by_name: dict[str, dict[str, Any]] = {}
    for c in old_rows:
        by_name.setdefault(norm(c.name), _plain(c, keys))

    db.execute(delete(Cost).where(Cost.project_id == project_id))
    for row in ep.rows:
        old = by_name.get(norm(row.get("name")))
        values = _merge_plan_fields(row, ep.mapped_fields, old, COST_PLAN_DEFAULTS)
        actual = _pick(row, "actual_amount", None) if "actual_amount" in ep.mapped_fields else None
        db.add(Cost(project_id=project_id, **values,
                    actual_amount=actual if actual is not None else ((old or {}).get("actual_amount") or 0.0),
                    source_row=row.get("_row")))
    return len(ep.rows)


def _replace_simple(db: Session, project_id: int, model, ep: EntityPlan, defaults: dict[str, Any]) -> int:
    db.execute(delete(model).where(model.project_id == project_id))
    for row in ep.rows:
        values = {k: _pick(row, k, d) for k, d in defaults.items()}
        if model is Resource:
            values["notes"] = " ".join(x for x in (row.get("notes"), row.get("note_source")) if x) or ""
        db.add(model(project_id=project_id, **values))
    return len(ep.rows)


def _apply_entities(db: Session, project_id: int, plan: ImportPlan) -> dict[str, int]:
    stats = {"tasks": 0, "risks": 0, "costs": 0, "resources": 0, "methods": 0, "hsse": 0,
             "matched_id": 0, "matched_title": 0}
    e = plan.entities
    if e["tasks"].used:
        stats["tasks"] = _apply_tasks(db, project_id, e["tasks"], stats)
    if e["risks"].used:
        stats["risks"] = _apply_risks(db, project_id, e["risks"])
    if e["costs"].used:
        stats["costs"] = _apply_costs(db, project_id, e["costs"])
    if e["resources"].used:
        stats["resources"] = _replace_simple(db, project_id, Resource, e["resources"], RESOURCE_DEFAULTS)
    if e["methods"].used:
        stats["methods"] = _replace_simple(db, project_id, Method, e["methods"], METHOD_DEFAULTS)
    if e["hsse"].used:
        stats["hsse"] = _replace_simple(db, project_id, HsseMetric, e["hsse"], HSSE_DEFAULTS)
    return stats


def _task_date_range(plan: ImportPlan) -> tuple[str | None, str | None]:
    rows = plan.entities["tasks"].rows
    starts = [r["start_date"] for r in rows if r.get("start_date")]
    ends = [r["end_date"] for r in rows if r.get("end_date")]
    return (min(starts) if starts else None, max(ends) if ends else None)


NOTE_AFTER_IMPORT = "Đã nhập từ Excel. Vui lòng xác nhận các mốc và giá trị hợp đồng."


# ---- public API ------------------------------------------------------------------------------

def preview_matches(db: Session, project_id: int, plan: ImportPlan) -> dict[str, int]:
    """For the preview of an update: how many file rows will keep their actual data. Read only."""
    ep = plan.entities["tasks"]
    if not ep.used:
        return {}
    old = list(db.scalars(select(Task).where(Task.project_id == project_id)))
    ids = {t.source_id for t in old if t.source_id is not None}
    titles = {norm(t.title) for t in old}
    by_id = by_title = new = 0
    for row in ep.rows:
        if row.get("source_id") is not None:
            if row["source_id"] in ids:
                by_id += 1
            else:
                new += 1
        elif norm(row.get("title")) in titles:
            by_title += 1
        else:
            new += 1
    return {"by_id": by_id, "by_title": by_title, "new": new, "old_total": len(old)}


def import_into_project(db: Session, project_id: int, plan: ImportPlan) -> dict[str, int]:
    """Update an existing project from a newer version of its workbook."""
    if not plan.has_data and not plan.project:
        raise ImportFormatError("File không có dữ liệu hay thông tin dự án nào nhận ra được, nên không có gì để cập nhật.")
    try:
        project = db.get(Project, project_id)
        if project is None:
            raise ImportFormatError(f"Không tìm thấy dự án số {project_id}.")
        for key, value in plan.project.items():
            if key != "name" or value:
                setattr(project, key, value)
        start, end = _task_date_range(plan)
        project.start_date = start or project.start_date
        project.end_date = end or project.end_date
        project.source_file = plan.file_name
        project.notes = NOTE_AFTER_IMPORT
        stats = _apply_entities(db, project_id, plan)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return stats


def import_as_new_project(db: Session, plan: ImportPlan, name: str = "") -> tuple[Project, dict[str, int]]:
    """Create a new project from the workbook. Fields and sections the file does not have stay empty.

    The only thing that must exist is the project name: the one typed by the user, else the one in the file.
    """
    project_name = (name or "").strip() or str(plan.project.get("name") or "").strip()
    if not project_name:
        raise ImportFormatError("Chưa có tên dự án: file không ghi tên dự án và ô “Tên dự án” đang để trống. "
                                "Hãy nhập tên dự án.")
    try:
        p = plan.project
        start, end = _task_date_range(plan)
        project = repo.new_project({
            "name": project_name, "client": p.get("client") or "", "contractor": p.get("contractor") or "",
            "package_name": p.get("package_name") or "", "description": p.get("description") or "",
            "report_date": p.get("report_date") or date.today().isoformat(), "start_date": start, "end_date": end,
            "contract_value": 0, "prelim_budget": p.get("prelim_budget") or 0,
            "planned_progress": p.get("planned_progress") or 0, "source_file": plan.file_name,
            "notes": NOTE_AFTER_IMPORT})
        db.add(project)
        db.flush()  # assigns project.id
        stats = _apply_entities(db, project.id, plan)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return project, stats
