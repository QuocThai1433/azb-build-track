"""Audit log: who did what, when, from where.

The signed-in user and the client address are kept in a context variable that the request middleware
sets, so repositories can log create / update / delete without every route passing the user down.
Rows are only ever added; the database refuses UPDATE and DELETE on audit_logs.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog

ACTIONS = ("create", "update", "delete", "login", "logout", "login_failed", "import", "export", "approve",
           "reject", "denied")


@dataclass(frozen=True)
class Actor:
    user_id: int | None = None
    username: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


_actor: ContextVar[Actor] = ContextVar("audit_actor", default=Actor())


def set_actor(actor: Actor):
    """Remember who is acting for the current request. Returns a token for reset_actor."""
    return _actor.set(actor)


def reset_actor(token) -> None:
    _actor.reset(token)


def current_actor() -> Actor:
    return _actor.get()


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def add(db: Session, action: str, entity_type: str | None = None, entity_id: int | None = None,
        project_id: int | None = None, old: Any = None, new: Any = None, actor: Actor | None = None) -> None:
    """Add one audit row to the session. The caller commits (so it lands with the change it describes)."""
    who = actor or current_actor()
    db.add(AuditLog(user_id=who.user_id, username=who.username, action=action, entity_type=entity_type,
                    entity_id=entity_id, project_id=project_id, old_value=_dump(old), new_value=_dump(new),
                    ip_address=who.ip_address, user_agent=(who.user_agent or "")[:300] or None,
                    created_at=datetime.now().isoformat(timespec="seconds")))


def record(db: Session, *args, **kwargs) -> None:
    """add() and commit, for events that have no other change to commit with (login, export, ...)."""
    add(db, *args, **kwargs)
    db.commit()


def diff(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the fields that changed, so an update row is short."""
    keys = [k for k in new if old.get(k) != new.get(k)]
    return {k: old.get(k) for k in keys}, {k: new.get(k) for k in keys}
