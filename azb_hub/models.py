"""ORM models.

Version 0002: the app holds many projects. Every data table has a ``project_id`` that points to
``project.id``; deleting a project deletes its rows (ON DELETE CASCADE).
"""
from __future__ import annotations

from sqlalchemy import REAL, Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint, event, false, select, true
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _project_fk(table: str):
    return mapped_column(Integer, ForeignKey("project.id", ondelete="CASCADE", name=f"fk_{table}_project_id"),
                         nullable=False, index=True)


class Project(Base):
    __tablename__ = "project"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str | None] = mapped_column(Text, unique=True)
    client: Mapped[str | None] = mapped_column(Text)
    contractor: Mapped[str | None] = mapped_column(Text)
    package_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[str | None] = mapped_column(Text)
    report_date: Mapped[str | None] = mapped_column(Text)
    contract_value: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    prelim_budget: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    planned_progress: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    source_file: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default="active")
    construction_status: Mapped[str] = mapped_column(Text, nullable=False, default="dang_thi_cong",
                                                     server_default="dang_thi_cong")
    created_at: Mapped[str | None] = mapped_column(Text)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("idx_tasks_source_id", "source_id"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("tasks")
    source_id: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str | None] = mapped_column(Text, default="Chi tiết", server_default="Chi tiết")
    planned_days: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    start_date: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[str | None] = mapped_column(Text)
    duration_calculated: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    schedule_check: Mapped[str | None] = mapped_column(Text)
    plan_progress: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    plan_status: Mapped[str | None] = mapped_column(Text)
    tet_flag: Mapped[str | None] = mapped_column(Text)
    float_days: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    actual_progress: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    actual_status: Mapped[str | None] = mapped_column(Text, default="Chưa cập nhật", server_default="Chưa cập nhật")
    owner: Mapped[str | None] = mapped_column(Text, default="", server_default="")
    actual_start_date: Mapped[str | None] = mapped_column(Text)
    actual_end_date: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text, default="Trung bình", server_default="Trung bình")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("resources")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    group_name: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    duration_months: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    start_date: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)


class Cost(Base):
    __tablename__ = "costs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("costs")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, default="Chi phí Prelim", server_default="Chi phí Prelim")
    unit: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    unit_price: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    budget_amount: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    actual_amount: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None] = mapped_column(Integer)
    approval_status: Mapped[str] = mapped_column(Text, nullable=False, default="da_duyet", server_default="da_duyet")
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[str | None] = mapped_column(Text)
    approval_note: Mapped[str | None] = mapped_column(Text)


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("risks")
    source_id: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    basis: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text, default="Trung bình", server_default="Trung bình")
    recommendation: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text, default="", server_default="")
    due_date: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text, default="Chưa xử lý", server_default="Chưa xử lý")
    created_at: Mapped[str | None] = mapped_column(Text)


class Method(Base):
    __tablename__ = "methods"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("methods")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    specification: Mapped[str | None] = mapped_column(Text)
    schedule: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)


class HsseMetric(Base):
    __tablename__ = "hsse_metrics"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("hsse_metrics")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float | None] = mapped_column(REAL, default=0.0, server_default="0")
    unit: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class SafetyLog(Base):
    __tablename__ = "safety_logs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("safety_logs")
    log_date: Mapped[str] = mapped_column(Text, nullable=False)
    log_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    people_affected: Mapped[int | None] = mapped_column(Integer, default=0, server_default="0")
    severity: Mapped[str | None] = mapped_column(Text, default="Thấp", server_default="Thấp")
    status: Mapped[str | None] = mapped_column(Text, default="Đã ghi nhận", server_default="Đã ghi nhận")
    reporter: Mapped[str | None] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[str | None] = mapped_column(Text)


class Diary(Base):
    __tablename__ = "diary"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = _project_fk("diary")
    log_date: Mapped[str] = mapped_column(Text, nullable=False)
    weather: Mapped[str | None] = mapped_column(Text)
    worker_count: Mapped[int | None] = mapped_column(Integer, default=0, server_default="0")
    completed_work: Mapped[str] = mapped_column(Text, nullable=False)
    issues: Mapped[str | None] = mapped_column(Text)
    reporter: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)


class ImportAlias(Base):
    """A choice the user made in the import preview, remembered for later files.

    kind "column": a header text (normalised) -> a field key, or "" to ignore that column.
    kind "sheet":  a sheet name (normalised) -> belongs to ``entity``.
    These belong to the whole app, not to one project.
    """
    __tablename__ = "import_aliases"
    __table_args__ = (UniqueConstraint("kind", "entity", "text_norm", name="uq_import_alias"),
                      {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    text_norm: Mapped[str] = mapped_column(Text, nullable=False)
    text_shown: Mapped[str | None] = mapped_column(Text)
    field: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[str | None] = mapped_column(Text)


PROJECT_DATA_MODELS = (Task, Resource, Cost, Risk, Method, HsseMetric, SafetyLog, Diary)


@event.listens_for(Project, "before_insert")
def _fill_slug(_mapper, connection, project: Project) -> None:
    """Every new project gets a unique URL slug made from its name (kept when the project is renamed)."""
    from . import slugs
    if not project.slug:
        taken = set(connection.execute(select(Project.slug)).scalars())
        project.slug = slugs.unique_slug(project.name, taken)
    slugs.clear_cache()


class User(Base):
    """A person who signs in. role: admin / giam_doc / nhan_vien (see auth.py)."""
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="nhan_vien", server_default="nhan_vien")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                       server_default=false())
    created_at: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[str | None] = mapped_column(Text)


class ProjectMember(Base):
    """Which staff member works on which project."""
    __tablename__ = "project_members"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE",
                                                             name="fk_project_members_user_id"), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("project.id", ondelete="CASCADE",
                                                                name="fk_project_members_project_id"),
                                            primary_key=True)
    role_in_project: Mapped[str] = mapped_column(Text, nullable=False, default="Thành viên",
                                                 server_default="Thành viên")


class AuditLog(Base):
    """Append-only history of changes. The database refuses UPDATE and DELETE (see migration 0005)."""
    __tablename__ = "audit_logs"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, index=True)
