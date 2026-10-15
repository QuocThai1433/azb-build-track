"""Undo a logged update from the audit log page: admin only, and never over a later edit."""
import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from azb_hub import auth
from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import AuditLog, Project, User


def _make_user(username: str, role: str, password: str = "Mat-khau-123") -> None:
    with SessionLocal() as db:
        if repo.get_user_by_username(db, username) is None:
            db.add(User(username=username, full_name=username, role=role, password_hash=auth.hash_password(password),
                        is_active=True))
            db.commit()


def _login(username: str, password: str = "Mat-khau-123") -> TestClient:
    from azb_hub.main import app
    c = TestClient(app, follow_redirects=False)
    assert c.post("/login", data={"username": username, "password": password}).status_code == 303
    return c


def _new_project(client, name: str) -> Project:
    r = client.post("/projects/new", data={"name": name})
    slug = re.match(r"^/([a-z0-9-]+)/$", r.headers["location"]).group(1)
    with SessionLocal() as db:
        return db.scalar(select(Project).where(Project.slug == slug))


def _rename(project_id: int, name: str) -> int:
    """Rename a project the way the app does, and return the id of the update row it logged."""
    with SessionLocal() as db:
        repo.update(db, db.get(Project, project_id), {"name": name})
        return db.scalar(select(AuditLog.id).where(AuditLog.action == "update", AuditLog.entity_type == "project",
                                                   AuditLog.entity_id == project_id).order_by(AuditLog.id.desc()))


def _name(project_id: int) -> str:
    with SessionLocal() as db:
        return db.get(Project, project_id).name


def test_admin_can_undo_an_update(client):
    p = _new_project(client, "Dự án hoàn tác")
    log_id = _rename(p.id, "Tên nhập sai")
    r = client.post(f"/audit-logs/{log_id}/revert")
    assert r.status_code == 303 and r.headers["location"] == "/audit-logs"
    assert _name(p.id) == "Dự án hoàn tác"
    with SessionLocal() as db:                                   # the undo itself is logged
        assert db.scalar(select(AuditLog).where(AuditLog.action == "update", AuditLog.entity_id == p.id)
                         .order_by(AuditLog.id.desc())).new_value == '{"name": "Dự án hoàn tác"}'


def test_undo_is_refused_when_the_record_changed_since(client):
    p = _new_project(client, "Dự án bị sửa tiếp")
    old_log = _rename(p.id, "Lần sửa đầu")
    _rename(p.id, "Lần sửa sau")
    client.post(f"/audit-logs/{old_log}/revert")
    assert _name(p.id) == "Lần sửa sau"                          # the later edit is not overwritten


def test_only_admin_can_undo(client):
    p = _new_project(client, "Dự án giám đốc")
    log_id = _rename(p.id, "Đổi tên")
    _make_user("gd-revert", auth.GIAM_DOC)
    director = _login("gd-revert")
    assert director.post(f"/audit-logs/{log_id}/revert").status_code == 403
    assert _name(p.id) == "Đổi tên"
