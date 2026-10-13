from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = Path(os.environ.get("AZB_DB_PATH") or INSTANCE_DIR / "project_manager.db")
SEED_PATH = DATA_DIR / "seed_data.json"
MIGRATIONS_DIR = BASE_DIR / "migrations"


class Base(DeclarativeBase):
    pass


DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


# Repositories commit explicitly, so objects stay readable after the transaction ends.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one Session per request."""
    with SessionLocal() as session:
        yield session


def run_migrations() -> None:
    """Bring the database to the latest schema.

    * Fresh database: run every migration.
    * Database created by the old Flask version (tables exist, no alembic_version): add the old
      ``priority`` column if it is missing, mark it as revision 0001 (its schema), then upgrade.
    * Before any upgrade of a database that already has data, save a backup in instance/backups.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "tasks" in tables and "alembic_version" not in tables:
        columns = {c["name"] for c in inspector.get_columns("tasks")}
        if "priority" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'Trung bình'"))
        command.stamp(cfg, "0001")

    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current is not None and current != head:
        from .services.backup import create_backup
        create_backup(label="truoc_nang_cap")
    command.upgrade(cfg, "head")
