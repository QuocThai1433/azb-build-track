"""Baseline: the schema created by the Flask version of AZB Project Hub.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _real(name):
    return sa.Column(name, sa.REAL(), server_default=sa.text("0"))


def _table(name, *columns):
    op.create_table(name, *columns, sqlite_autoincrement=True)


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("client", sa.Text()),
        sa.Column("contractor", sa.Text()),
        sa.Column("package_name", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("start_date", sa.Text()),
        sa.Column("end_date", sa.Text()),
        sa.Column("report_date", sa.Text()),
        _real("contract_value"),
        _real("prelim_budget"),
        _real("planned_progress"),
        sa.Column("source_file", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint("id = 1"),
    )
    _table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer()),
        sa.Column("category", sa.Text()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), server_default="Chi tiết"),
        _real("planned_days"),
        sa.Column("start_date", sa.Text()),
        sa.Column("end_date", sa.Text()),
        _real("duration_calculated"),
        sa.Column("schedule_check", sa.Text()),
        _real("plan_progress"),
        sa.Column("plan_status", sa.Text()),
        sa.Column("tet_flag", sa.Text()),
        _real("float_days"),
        sa.Column("notes", sa.Text()),
        _real("actual_progress"),
        sa.Column("actual_status", sa.Text(), server_default="Chưa cập nhật"),
        sa.Column("owner", sa.Text(), server_default=""),
        sa.Column("actual_start_date", sa.Text()),
        sa.Column("actual_end_date", sa.Text()),
        sa.Column("updated_at", sa.Text()),
        sa.Column("priority", sa.Text(), server_default="Trung bình"),
    )
    op.create_index("idx_tasks_source_id", "tasks", ["source_id"])
    _table(
        "resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text()),
        sa.Column("group_name", sa.Text()),
        _real("quantity"),
        _real("duration_months"),
        sa.Column("start_date", sa.Text()),
        sa.Column("end_date", sa.Text()),
        sa.Column("unit", sa.Text()),
        _real("cost"),
        sa.Column("notes", sa.Text()),
    )
    _table(
        "costs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), server_default="Chi phí Prelim"),
        sa.Column("unit", sa.Text()),
        _real("quantity"),
        _real("unit_price"),
        _real("budget_amount"),
        _real("actual_amount"),
        sa.Column("notes", sa.Text()),
        sa.Column("source_row", sa.Integer()),
    )
    _table(
        "risks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer()),
        sa.Column("category", sa.Text()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("basis", sa.Text()),
        sa.Column("severity", sa.Text(), server_default="Trung bình"),
        sa.Column("recommendation", sa.Text()),
        sa.Column("owner", sa.Text(), server_default=""),
        sa.Column("due_date", sa.Text()),
        sa.Column("status", sa.Text(), server_default="Chưa xử lý"),
        sa.Column("created_at", sa.Text()),
    )
    _table(
        "methods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text()),
        _real("quantity"),
        sa.Column("specification", sa.Text()),
        sa.Column("schedule", sa.Text()),
        sa.Column("source", sa.Text()),
    )
    _table(
        "hsse_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        _real("value"),
        sa.Column("unit", sa.Text()),
        sa.Column("notes", sa.Text()),
    )
    _table(
        "safety_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("log_date", sa.Text(), nullable=False),
        sa.Column("log_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("people_affected", sa.Integer(), server_default=sa.text("0")),
        sa.Column("severity", sa.Text(), server_default="Thấp"),
        sa.Column("status", sa.Text(), server_default="Đã ghi nhận"),
        sa.Column("reporter", sa.Text(), server_default=""),
        sa.Column("created_at", sa.Text()),
    )
    _table(
        "diary",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("log_date", sa.Text(), nullable=False),
        sa.Column("weather", sa.Text()),
        sa.Column("worker_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("completed_work", sa.Text(), nullable=False),
        sa.Column("issues", sa.Text()),
        sa.Column("reporter", sa.Text()),
        sa.Column("created_at", sa.Text()),
    )


def downgrade() -> None:
    for table in ("diary", "safety_logs", "hsse_metrics", "methods", "risks", "costs", "resources", "tasks", "project"):
        op.drop_table(table)
