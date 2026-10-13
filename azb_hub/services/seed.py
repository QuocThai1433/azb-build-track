"""First-run data: when the database has no project at all, load data/seed_data.json as project 1."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import SEED_PATH
from ..models import Cost, HsseMetric, Method, Project, Resource, Risk, Task

PROJECT_FIELDS = ["name", "client", "contractor", "package_name", "description", "start_date", "end_date",
                  "report_date", "contract_value", "prelim_budget", "planned_progress", "source_file", "notes"]
TASK_FIELDS = ["source_id", "category", "title", "task_type", "planned_days", "start_date", "end_date",
               "duration_calculated", "schedule_check", "plan_progress", "plan_status", "tet_flag", "float_days", "notes"]
RESOURCE_FIELDS = ["name", "resource_type", "group_name", "quantity", "duration_months", "start_date", "end_date",
                   "unit", "cost", "notes"]
METHOD_FIELDS = ["name", "unit", "quantity", "specification", "schedule", "source"]


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(Project)) or not SEED_PATH.exists():
        return False
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    now = datetime.now().isoformat(timespec="seconds")

    p = seed["project"]
    values = {k: p.get(k) for k in PROJECT_FIELDS}
    for key in ("contract_value", "prelim_budget", "planned_progress"):
        values[key] = p.get(key, 0)
    project = repo.new_project(values)
    db.add(project)
    db.flush()  # assigns project.id
    pid = project.id

    for t in seed.get("tasks", []):
        row = {k: t.get(k) for k in TASK_FIELDS}
        for key in ("planned_days", "duration_calculated", "plan_progress", "float_days"):
            row[key] = t.get(key, 0)
        db.add(Task(project_id=pid, actual_progress=0, actual_status="Chưa cập nhật", **row))
    for r in seed.get("resources", []):
        db.add(Resource(project_id=pid, **{k: r.get(k) for k in RESOURCE_FIELDS}))
    for c in seed.get("costs", []):
        db.add(Cost(project_id=pid, name=c.get("name"), category=c.get("category"), unit=c.get("unit"),
                    quantity=c.get("quantity", 0), unit_price=c.get("unit_price", 0),
                    budget_amount=c.get("budget_amount", 0), actual_amount=0,
                    notes=c.get("notes"), source_row=c.get("source_row")))
    for r in seed.get("risks", []):
        db.add(Risk(project_id=pid, source_id=r.get("source_id"), category=r.get("category"),
                    description=r.get("description"), basis=r.get("basis"), severity=r.get("severity"),
                    recommendation=r.get("recommendation"), owner="", due_date=None, status="Chưa xử lý",
                    created_at=now))
    for m in seed.get("methods", []):
        db.add(Method(project_id=pid, **{k: m.get(k) for k in METHOD_FIELDS}))
    for h in seed.get("hsse_metrics", []):
        db.add(HsseMetric(project_id=pid, name=h.get("name"), value=h.get("value", 0), unit=h.get("unit"),
                          notes=h.get("notes")))
    db.commit()
    return True
