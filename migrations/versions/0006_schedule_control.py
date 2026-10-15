"""Schedule control: task dependencies, baselines, working calendar, task weight and progress snapshots.

* task_dependencies: predecessor -> successor (FS/SS/FF/SF + lag in working days).
* baselines / baseline_tasks: frozen copies of the planned dates.
* holidays + project.work_days: the working calendar used by the critical-path calculation.
* tasks.weight: share of a task in the project progress (default 1, so old data behaves as before).
* progress_snapshots: daily planned/actual progress for the S-curve history.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _fk(table: str) -> sa.Column:
    return sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="CASCADE",
                                                               name=f"fk_{table}_project_id"), nullable=False)


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("weight", sa.REAL(), server_default="1"))
    with op.batch_alter_table("project") as batch:
        batch.add_column(sa.Column("work_days", sa.Text(), nullable=False, server_default="0,1,2,3,4,5"))

    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _fk("task_dependencies"),
        sa.Column("predecessor_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("successor_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dep_type", sa.Text(), nullable=False, server_default="FS"),
        sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("predecessor_id", "successor_id", name="uq_task_dependency"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_task_dependencies_project_id", "task_dependencies", ["project_id"])
    op.create_index("ix_task_dependencies_successor_id", "task_dependencies", ["successor_id"])

    op.create_table(
        "baselines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _fk("baselines"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text()),
        sa.Column("created_by", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_baselines_project_id", "baselines", ["project_id"])

    op.create_table(
        "baseline_tasks",
        sa.Column("baseline_id", sa.Integer(), sa.ForeignKey("baselines.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("start_date", sa.Text()),
        sa.Column("end_date", sa.Text()),
        sa.Column("weight", sa.REAL(), server_default="1"),
    )

    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _fk("holidays"),
        sa.Column("day", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default=""),
        sa.UniqueConstraint("project_id", "day", name="uq_holiday_day"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_holidays_project_id", "holidays", ["project_id"])

    op.create_table(
        "progress_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _fk("progress_snapshots"),
        sa.Column("day", sa.Text(), nullable=False),
        sa.Column("planned", sa.REAL(), nullable=False, server_default="0"),
        sa.Column("actual", sa.REAL(), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.REAL(), nullable=False, server_default="0"),
        sa.UniqueConstraint("project_id", "day", name="uq_snapshot_day"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_progress_snapshots_project_id", "progress_snapshots", ["project_id"])


def downgrade() -> None:
    for table in ("progress_snapshots", "holidays", "baseline_tasks", "baselines", "task_dependencies"):
        op.drop_table(table)
    with op.batch_alter_table("project") as batch:
        batch.drop_column("work_days")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("weight")
