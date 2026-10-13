"""Many projects in one database.

* project: drop the CHECK (id = 1) rule, add status ('active' / 'archived') and created_at.
* every data table: add project_id -> project.id (ON DELETE CASCADE) + an index.
  Existing rows belong to project 1, the only project that existed before.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CHILD_TABLES = ["tasks", "resources", "costs", "risks", "methods", "hsse_metrics", "safety_logs", "diary"]
PROJECT_COLUMNS = ("id, name, client, contractor, package_name, description, start_date, end_date, report_date, "
                   "contract_value, prelim_budget, planned_progress, source_file, notes")


def upgrade() -> None:
    # SQLite cannot drop a CHECK constraint, so rebuild the project table.
    op.execute("""
        CREATE TABLE project_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, client TEXT, contractor TEXT, package_name TEXT, description TEXT,
            start_date TEXT, end_date TEXT, report_date TEXT,
            contract_value REAL DEFAULT 0, prelim_budget REAL DEFAULT 0, planned_progress REAL DEFAULT 0,
            source_file TEXT, notes TEXT,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT
        )""")
    op.execute(f"INSERT INTO project_new ({PROJECT_COLUMNS}, created_at) "
               f"SELECT {PROJECT_COLUMNS}, datetime('now', 'localtime') FROM project")
    op.execute("DROP TABLE project")
    op.execute("ALTER TABLE project_new RENAME TO project")

    for table in CHILD_TABLES:
        # Pass 1: add the column with DEFAULT 1 so the copied rows land in project 1.
        with op.batch_alter_table(table, recreate="always", table_kwargs={"sqlite_autoincrement": True}) as batch:
            batch.add_column(sa.Column("project_id", sa.Integer(), nullable=False, server_default="1"))
        # Pass 2: drop the default (new rows must name their project) and add the FK + index.
        with op.batch_alter_table(table, recreate="always", table_kwargs={"sqlite_autoincrement": True}) as batch:
            batch.alter_column("project_id", existing_type=sa.Integer(), existing_nullable=False, server_default=None)
            batch.create_foreign_key(f"fk_{table}_project_id", "project", ["project_id"], ["id"], ondelete="CASCADE")
            batch.create_index(f"ix_{table}_project_id", ["project_id"])


def downgrade() -> None:
    raise NotImplementedError("Downgrade would merge every project into one. Restore a backup from instance/backups instead.")
