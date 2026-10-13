from alembic import context
from sqlalchemy import create_engine

from azb_hub import models  # noqa: F401  (registers the tables on Base.metadata)
from azb_hub.db import DB_PATH, Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    # A separate engine without the app's "PRAGMA foreign_keys = ON" hook: table rebuilds in
    # batch mode drop and re-create tables, which must not trigger ON DELETE CASCADE.
    engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run against the SQLite file.")
run_migrations_online()
