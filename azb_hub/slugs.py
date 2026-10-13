"""Project slugs: the readable part of a project URL (/<slug>/tasks).

Handlers keep receiving ``project_id: int``. The ``project`` URL convertor below turns the slug in the
URL into that id, and back again when a URL is built, so only this module knows slugs exist.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from starlette.convertors import Convertor, register_url_convertor

from .db import SessionLocal

RESERVED = {"new", "p", "projects", "static"}   # first URL segments the app already uses
_ID_BY_SLUG: dict[str, int] = {}
_SLUG_BY_ID: dict[int, str] = {}


def slugify(name: str) -> str:
    """'Nhà máy Xi măng Đồng Nai' -> 'nha-may-xi-mang-dong-nai'."""
    text = unicodedata.normalize("NFKD", (name or "").replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-") or "du-an"


def unique_slug(name: str, taken: set[str]) -> str:
    base = slugify(name)
    slug, n = base, 2
    while slug in taken or slug in RESERVED:
        slug, n = f"{base}-{n}", n + 1
    return slug


def clear_cache() -> None:
    _ID_BY_SLUG.clear()
    _SLUG_BY_ID.clear()


def _lookup(slug: str | None = None, project_id: int | None = None) -> tuple[int, str] | None:
    from .models import Project
    stmt = select(Project.id, Project.slug)
    stmt = stmt.where(Project.slug == slug) if slug is not None else stmt.where(Project.id == project_id)
    with SessionLocal() as db:
        row = db.execute(stmt).first()
    return (row[0], row[1]) if row and row[1] else None


class ProjectConvertor(Convertor):
    """slug <-> project id. An unknown slug becomes id 0, which load_project turns into a 404."""
    regex = r"[a-z0-9]+(?:-[a-z0-9]+)*"

    def convert(self, value: str) -> int:
        if value not in _ID_BY_SLUG:
            found = _lookup(slug=value)
            if found is None:
                return 0
            _ID_BY_SLUG[value] = found[0]
        return _ID_BY_SLUG[value]

    def to_string(self, value) -> str:
        pid = int(value)
        if pid not in _SLUG_BY_ID:
            found = _lookup(project_id=pid)
            if found is None:
                return str(pid)
            _SLUG_BY_ID[pid] = found[1]
        return _SLUG_BY_ID[pid]


register_url_convertor("project", ProjectConvertor())
