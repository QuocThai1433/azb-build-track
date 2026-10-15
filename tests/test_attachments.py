import pytest

from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import Attachment, Diary, Project, Risk, SafetyLog
from azb_hub.services import attachments as svc

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def ctx():
    with SessionLocal() as db:
        p = Project(name="Dự án đính kèm")
        db.add(p)
        db.commit()
        d = Diary(project_id=p.id, log_date="2026-01-05", completed_work="Đổ bê tông")
        h = SafetyLog(project_id=p.id, log_date="2026-01-05", log_type="Kiểm tra", description="Kiểm tra giàn giáo")
        r = Risk(project_id=p.id, description="Mưa kéo dài")
        db.add_all([d, h, r])
        db.commit()
        return {"pid": p.id, "slug": repo.get_project(db, p.id).slug, "diary": d.id, "hsse": h.id, "risk": r.id}


def upload(client, slug, entity_type, entity_id, name="anh.png", data=PNG):
    return client.post(f"/{slug}/attachments", data={"entity_type": entity_type, "entity_id": entity_id},
                       files=[("files", (name, data, "application/octet-stream"))])


def test_validate_rules():
    assert svc.validate("a.png", PNG) == ".png"
    for name, data in [("a.exe", b"MZ"), ("a.svg", b"<svg/>"), ("a.html", b"<html>"),
                       ("a.png", b"not a png"), ("a.pdf", b""), ("a.jpg", b"%PDF-1.4")]:
        with pytest.raises(svc.AttachmentError):
            svc.validate(name, data)
    assert svc.clean_filename(r"..\..\evil/../x<>.png") == "x.png"


def test_upload_download_and_delete_on_each_module(client, ctx):
    slug = ctx["slug"]
    for entity_type, key, page in [("diary", "diary", "diary"), ("safety_logs", "hsse", "hsse"),
                                   ("risks", "risk", "risks")]:
        r = upload(client, slug, entity_type, ctx[key])
        assert r.status_code == 303
        with SessionLocal() as db:
            att = db.query(Attachment).filter_by(project_id=ctx["pid"], entity_type=entity_type).one()
            assert svc.path_of(att).is_file()
            att_id = att.id
        got = client.get(f"/{slug}/attachments/{att_id}")
        assert got.status_code == 200 and got.content == PNG
        assert got.headers["x-content-type-options"] == "nosniff"
        assert att_id and f"/attachments/{att_id}" in client.get(f"/{slug}/{page}").text
        assert client.post(f"/{slug}/attachments/{att_id}/delete").status_code == 303
        with SessionLocal() as db:
            assert db.get(Attachment, att_id) is None
        assert not svc.path_of(att).exists()


def test_rejected_files_are_not_stored(client, ctx):
    r = upload(client, ctx["slug"], "diary", ctx["diary"], name="virus.exe", data=b"MZ")
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(Attachment).filter_by(project_id=ctx["pid"]).count() == 0


def test_cannot_attach_to_other_projects_record(client, ctx):
    with SessionLocal() as db:
        other = Project(name="Dự án khác")
        db.add(other)
        db.commit()
        other_slug = repo.get_project(db, other.id).slug
    upload(client, other_slug, "diary", ctx["diary"])             # diary entry belongs to ctx project
    with SessionLocal() as db:
        assert db.query(Attachment).count() == db.query(Attachment).filter_by(project_id=ctx["pid"]).count()
        assert db.query(Attachment).filter_by(project_id=other.id).count() == 0


def test_deleting_record_and_project_removes_files(client, ctx):
    upload(client, ctx["slug"], "diary", ctx["diary"])
    with SessionLocal() as db:
        att = db.query(Attachment).filter_by(project_id=ctx["pid"]).one()
        path = svc.path_of(att)
    assert path.is_file()
    assert client.post(f"/{ctx['slug']}/diary/{ctx['diary']}/delete").status_code == 303
    assert not path.exists()
    with SessionLocal() as db:
        assert db.query(Attachment).filter_by(project_id=ctx["pid"]).count() == 0

    upload(client, ctx["slug"], "risks", ctx["risk"])
    folder = svc.ATTACH_DIR / str(ctx["pid"])
    assert folder.exists()
    with SessionLocal() as db:
        repo.delete_project(db, ctx["pid"])
    assert not folder.exists()


def test_forbidden_action_becomes_a_dialog_not_json(client, ctx):
    from azb_hub import auth
    from azb_hub.models import User
    with SessionLocal() as db:
        staff = User(username="nv_dialog", full_name="NV", password_hash=auth.hash_password("Matkhau-12345"),
                     role="nhan_vien", is_active=True)
        db.add(staff)
        db.commit()
        db.execute(__import__("sqlalchemy").text(
            "insert into project_members(user_id, project_id) values (:u, :p)"), {"u": staff.id, "p": ctx["pid"]})
        db.commit()
    upload(client, ctx["slug"], "diary", ctx["diary"])            # uploaded by admin
    with SessionLocal() as db:
        att_id = db.query(Attachment).filter_by(project_id=ctx["pid"]).one().id

    from fastapi.testclient import TestClient
    from azb_hub.main import app
    with TestClient(app, follow_redirects=False) as c2:
        assert c2.post("/login", data={"username": "nv_dialog", "password": "Matkhau-12345"}).status_code == 303
        page = f"/{ctx['slug']}/diary"
        r = c2.post(f"/{ctx['slug']}/attachments/{att_id}/delete", headers={"referer": f"http://testserver{page}", "accept": "text/html"})
        assert r.status_code == 303 and r.headers["location"] == page
        assert "chỉ xóa được tệp do chính mình" in c2.get(page).text
        assert c2.get(page).text.count("denied-overlay") <= 1       # shown once, then consumed
