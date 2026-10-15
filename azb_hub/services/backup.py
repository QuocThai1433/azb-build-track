"""Database backups: a consistent copy of the SQLite file, made with SQLite's own backup API."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ..db import DB_PATH


def backups_dir() -> Path:
    return DB_PATH.parent / "backups"


def create_backup(label: str = "") -> Path:
    """Copy the live database to instance/backups/<name>_[<label>_]<YYYYMMDD_HHMMSS>.db and return the new path.

    sqlite3's backup() reads a consistent snapshot even while other connections are open,
    so a plain file copy (which can catch a half-written page) is not needed.
    """
    target_dir = backups_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{DB_PATH.stem}_{label + '_' if label else ''}{stamp}"
    target = target_dir / f"{base}.db"
    counter = 1
    while target.exists():
        target = target_dir / f"{base}_{counter}.db"
        counter += 1

    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def list_backups(limit: int = 5) -> list[dict]:
    folder = backups_dir()
    if not folder.exists():
        return []
    files = sorted(folder.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [{"name": f.name,
             "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
             "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")}
            for f in files]


AUTO_LABEL = "tu_dong"
AUTO_KEEP = 14                      # newest automatic backups kept; manual and pre-upgrade ones are never pruned
AUTO_INTERVAL_HOURS = 24


def backup_if_due(now: datetime | None = None) -> Path | None:
    """Make an automatic backup when the newest one is older than AUTO_INTERVAL_HOURS, then prune old ones."""
    now = now or datetime.now()
    folder = backups_dir()
    autos = sorted(folder.glob(f"{DB_PATH.stem}_{AUTO_LABEL}_*.db"), key=lambda p: p.stat().st_mtime) \
        if folder.exists() else []
    if autos and now - datetime.fromtimestamp(autos[-1].stat().st_mtime) < timedelta(hours=AUTO_INTERVAL_HOURS):
        return None
    created = create_backup(label=AUTO_LABEL)
    autos = sorted(folder.glob(f"{DB_PATH.stem}_{AUTO_LABEL}_*.db"), key=lambda p: p.stat().st_mtime)
    for old in autos[:-AUTO_KEEP]:
        old.unlink(missing_ok=True)
    return created
