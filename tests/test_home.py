"""The home page and its JSON search."""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from azb_hub import auth
from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import Project, User

SLUG1 = "nha-may-san-xuat-cac-san-pham-sau-thep"


def _new_project(client, name: str) -> Project:
    r = client.post("/projects/new", data={"name": name})
    slug = re.match(r"^/([a-z0-9-]+)/$", r.headers["location"]).group(1)
    with SessionLocal() as db:
        return db.scalar(select(Project).where(Project.slug == slug))


def _staff(username: str, projects) -> TestClient:
    from azb_hub.main import app
    with SessionLocal() as db:
        user = repo.get_user_by_username(db, username)
        if user is None:
            user = User(username=username, full_name=username, role=auth.NHAN_VIEN, is_active=True,
                        password_hash=auth.hash_password("Mat-khau-123"))
            db.add(user)
            db.flush()
        repo.set_memberships(db, user.id, set(projects))
        db.commit()
    c = TestClient(app, follow_redirects=False)
    assert c.post("/login", data={"username": username, "password": "Mat-khau-123"}).status_code == 303
    return c


def _names(response) -> list[str]:
    return [p["name"] for p in response.json()["projects"]]


def test_home_shows_kpis_and_cards_for_the_director(client):
    page = client.get("/").text
    assert "Số dự án" in page and "Rủi ro mức Cao" in page
    assert f'href="/{SLUG1}/"' in page
    assert "Tìm kiếm" in page and 'id="homeQ"' in page


def test_search_ignores_accents_and_case(client):
    assert any("Nhà máy" in n for n in _names(client.get("/api/projects/search?q=nha may THEP")))
    assert _names(client.get("/api/projects/search?q=khong-co-du-an-nao-ten-nay")) == []
    body = client.get("/api/projects/search?q=").json()
    assert body["total"] >= 1 and {"id", "name", "url", "status_label", "progress", "late"} <= set(body["projects"][0])


def test_search_by_client_and_server_rendered_filter(client):
    project = _new_project(client, "Kho vận Bình Dương")
    client.post(f"/{project.slug}/project", data={"name": "Kho vận Bình Dương", "client": "Công ty Hòa Phát"})
    assert "Kho vận Bình Dương" in _names(client.get("/api/projects/search?q=hoa phat"))
    assert "Kho vận Bình Dương" in client.get("/?q=hoa+phat").text
    assert "Nhà máy" not in client.get("/?q=hoa+phat").text.split('id="homeGrid"')[1]


def test_construction_status_is_editable_and_filterable(client):
    project = _new_project(client, "Dự án tạm dừng thử")
    client.post(f"/{project.slug}/project", data={"name": "Dự án tạm dừng thử", "construction_status": "tam_dung"})
    paused = _names(client.get("/api/projects/search?status=tam_dung"))
    assert "Dự án tạm dừng thử" in paused
    assert "Dự án tạm dừng thử" not in _names(client.get("/api/projects/search?status=hoan_thanh"))
    client.post(f"/{project.slug}/project", data={"name": "Dự án tạm dừng thử", "construction_status": "bậy"})
    with SessionLocal() as db:
        assert db.get(Project, project.id).construction_status == "tam_dung"          # invalid value is ignored


def test_late_project_is_flagged(client):
    project = _new_project(client, "Dự án trễ hạn thử")
    client.post(f"/{project.slug}/project", data={"name": "Dự án trễ hạn thử", "end_date": "2020-01-01"})
    card = next(p for p in client.get("/api/projects/search?q=tre han thu").json()["projects"] if p["id"] == project.id)
    assert card["late"] is True and card["days_left"] < 0
    client.post(f"/{project.slug}/project", data={"name": "Dự án trễ hạn thử", "end_date": "2020-01-01",
                                                   "construction_status": "hoan_thanh"})
    card = next(p for p in client.get("/api/projects/search?q=tre han thu").json()["projects"] if p["id"] == project.id)
    assert card["late"] is False                                                        # finished is never late


def test_staff_search_and_home_only_show_assigned_projects(client):
    other = _new_project(client, "Dự án bí mật của giám đốc")
    staff = _staff("nv-home", {1})
    assert "Dự án bí mật của giám đốc" not in _names(staff.get("/api/projects/search?q=bi mat"))
    page = staff.get("/").text
    assert "Dự án bí mật của giám đốc" not in page and "Số dự án" not in page           # no director KPI row
    assert f'href="/{SLUG1}/"' in page
    assert staff.get(f"/{other.slug}/").status_code == 403
    assert "Dự án bí mật của giám đốc" in client.get("/").text


def test_staff_without_projects_sees_the_empty_state(client):
    staff = _staff("nv-trong", set())
    assert "Bạn chưa được giao dự án nào" in staff.get("/").text
    assert staff.get("/api/projects/search").json() == {"total": 0, "projects": []}


def test_recent_projects_follow_the_last_opened(client):
    project = _new_project(client, "Dự án mở gần nhất")
    client.get(f"/{project.slug}/gantt")
    assert "Dự án gần đây" in client.get("/").text
    assert client.get("/?q=gan+nhat").text.count("Dự án gần đây") == 0                   # hidden while searching


def test_project_names_are_escaped_on_the_home_page(client):
    _new_project(client, "<script>alert(1)</script>Kho")
    page = client.get("/").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)" in page


def test_sign_in_lands_on_the_home_page(client):
    from azb_hub.main import app
    c = TestClient(app, follow_redirects=False)
    r = c.post("/login", data={"username": "admin", "password": "Admin-test-123"})
    assert r.headers["location"] == "/"
    assert c.get("/").status_code == 200


def test_guest_sees_the_landing_page_not_project_data(client):
    from azb_hub.main import app
    anon = TestClient(app, follow_redirects=False)
    r = anon.get("/")
    assert r.status_code == 200
    assert "Quản Lý Kế Hoạch Thi Công" in r.text and 'href="/login"' in r.text
    assert f'href="/{SLUG1}/"' not in r.text
    assert anon.get("/?q=a").status_code == 200
    assert anon.get(f"/{SLUG1}/").status_code == 303
