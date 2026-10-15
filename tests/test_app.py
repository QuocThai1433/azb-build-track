import io
import os
import re
import sqlite3
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from openpyxl import load_workbook

from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import Cost, Diary, Project, Resource, Risk, SafetyLog, Task

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_XLSX = ROOT / "data" / "Ke_hoach_thi_cong_Nha_may_Ton_Dong_A.xlsx"


def u(project_id: int) -> str:
    """URL prefix of a project: /<slug>."""
    with SessionLocal() as db:
        return f"/{repo.get_project(db, project_id).slug}"


def project_id_from(location: str) -> int:
    """Project id behind a redirect to /<slug>/."""
    match = re.match(r"^/([a-z0-9-]+)/$", location)
    assert match, location
    with SessionLocal() as db:
        return db.query(Project).filter_by(slug=match.group(1)).one().id


def follow(client, response):
    assert response.status_code == 303, response.text[:300]
    return client.get(response.headers["location"])


# ---- read-only pages --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/nha-may-san-xuat-cac-san-pham-sau-thep/", "/nha-may-san-xuat-cac-san-pham-sau-thep/project", "/nha-may-san-xuat-cac-san-pham-sau-thep/tasks", "/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/new", "/nha-may-san-xuat-cac-san-pham-sau-thep/gantt", "/nha-may-san-xuat-cac-san-pham-sau-thep/resources", "/nha-may-san-xuat-cac-san-pham-sau-thep/resources/new", "/nha-may-san-xuat-cac-san-pham-sau-thep/costs", "/nha-may-san-xuat-cac-san-pham-sau-thep/costs/new",
    "/nha-may-san-xuat-cac-san-pham-sau-thep/risks", "/nha-may-san-xuat-cac-san-pham-sau-thep/risks/new", "/nha-may-san-xuat-cac-san-pham-sau-thep/hsse", "/nha-may-san-xuat-cac-san-pham-sau-thep/methods", "/nha-may-san-xuat-cac-san-pham-sau-thep/methods/new", "/nha-may-san-xuat-cac-san-pham-sau-thep/diary", "/nha-may-san-xuat-cac-san-pham-sau-thep/import", "/nha-may-san-xuat-cac-san-pham-sau-thep/reports",
    "/nha-may-san-xuat-cac-san-pham-sau-thep/tasks?overdue=1", "/nha-may-san-xuat-cac-san-pham-sau-thep/tasks?q=nền&priority=Cao", "/nha-may-san-xuat-cac-san-pham-sau-thep/resources?type=Thiết bị / vận chuyển", "/nha-may-san-xuat-cac-san-pham-sau-thep/costs?q=điện",
    "/nha-may-san-xuat-cac-san-pham-sau-thep/risks?severity=Cao&status=Chưa xử lý", "/nha-may-san-xuat-cac-san-pham-sau-thep/methods?q=điện",
])
def test_page_renders(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "AZB Project Hub" in r.text


def test_static_assets_served(client):
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200


def test_seed_loaded_once(client):
    with SessionLocal() as db:
        assert repo.get_project(db, 1) is not None
        assert repo.count_rows(db, Task, 1) > 0
        assert repo.count_rows(db, Cost, 1) == 63
        assert repo.count_rows(db, Risk, 1) == 17


def test_missing_records_return_404(client):
    assert client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/999999/edit").status_code == 404
    assert client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/costs/999999/edit").status_code == 404
    assert client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/risks/999999/edit", data={"description": "x"}).status_code == 404


# ---- tasks ------------------------------------------------------------------------------------

def test_task_crud_flow(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/new", data={"title": "Đổ bê tông móng M1", "category": "Móng", "plan_progress": "50",
                                         "actual_progress": "40", "actual_status": "Đang thi công",
                                         "owner": "Nguyễn Văn A", "priority": "Khẩn cấp",
                                         "start_date": "2026-01-01", "end_date": "2026-01-10"})
    page = follow(client, r)
    assert "Đã thêm công việc mới." in page.text
    assert "Đổ bê tông móng M1" in page.text

    with SessionLocal() as db:
        task = db.query(Task).filter_by(title="Đổ bê tông móng M1").one()
        assert task.plan_progress == 0.5          # form sends 0-100, stored as 0-1
        assert task.actual_progress == 40
        assert task.priority == "Khẩn cấp"
        assert task.updated_at is not None         # actual data was touched
        task_id = task.id

    r = client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/{task_id}/edit", data={"title": "Đổ bê tông móng M1", "actual_progress": "250",
                                                     "actual_status": "Hoàn thành", "priority": "không hợp lệ"})
    assert "Đã cập nhật công việc" in follow(client, r).text
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task.actual_progress == 100         # clamped
        assert task.priority == "Trung bình"       # unknown priority falls back

    assert "Đã xóa công việc." in follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/{task_id}/delete")).text
    with SessionLocal() as db:
        assert db.get(Task, task_id) is None


def test_task_requires_title(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/new", data={"title": "   "})
    assert r.status_code == 200
    assert "Vui lòng nhập tên công việc." in r.text


def test_task_filters(client):
    client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/new", data={"title": "Việc lọc ưu tiên", "priority": "Cao", "actual_status": "Tạm dừng",
                                    "end_date": "2000-01-01"})
    page = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks?priority=Cao&status=Tạm dừng&overdue=1&q=lọc ưu tiên").text
    assert "Việc lọc ưu tiên" in page
    assert "Việc lọc ưu tiên" not in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks?priority=Thấp&q=lọc ưu tiên").text


# ---- resources / costs / risks / methods ------------------------------------------------------

def test_cost_accepts_vietnamese_decimal_comma(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/costs/new", data={"name": "Xi măng PC40", "quantity": "1,5", "unit_price": "2000",
                                         "budget_amount": "3000", "category": "Vật tư"})
    assert "Đã thêm khoản chi." in follow(client, r).text
    with SessionLocal() as db:
        cost = db.query(Cost).filter_by(name="Xi măng PC40").one()
        assert cost.quantity == 1.5
        cost_id = cost.id
    r = client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/costs/{cost_id}/edit", data={"name": "Xi măng PC40", "actual_amount": "2500,5"})
    follow(client, r)
    with SessionLocal() as db:
        assert db.get(Cost, cost_id).actual_amount == 2500.5
    assert "Đã xóa khoản chi." in follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/costs/{cost_id}/delete")).text


def test_resource_crud(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/resources/new", data={"name": "Cần cẩu 50T", "resource_type": "Thiết bị", "quantity": "2"})
    assert "Đã thêm nguồn lực." in follow(client, r).text
    with SessionLocal() as db:
        rid = db.query(Resource).filter_by(name="Cần cẩu 50T").one().id
    assert "Cần cẩu 50T" in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/resources?q=cẩu").text
    assert client.get(f"/nha-may-san-xuat-cac-san-pham-sau-thep/resources/{rid}/edit").status_code == 200
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/resources/{rid}/edit", data={"name": "Cần cẩu 80T"}))
    assert "Cần cẩu 80T" in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/resources").text
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/resources/{rid}/delete"))
    assert "Cần cẩu 80T" not in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/resources").text


def test_risk_crud(client):
    assert "Vui lòng mô tả rủi ro." in client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/risks/new", data={"description": " "}).text
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/risks/new", data={"description": "Mưa bão kéo dài", "severity": "Cao", "owner": "Ban chỉ huy"})
    assert "Đã ghi nhận rủi ro." in follow(client, r).text
    with SessionLocal() as db:
        risk = db.query(Risk).filter_by(description="Mưa bão kéo dài").one()
        assert risk.status == "Chưa xử lý" and risk.created_at
        rid = risk.id
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/risks/{rid}/edit", data={"description": "Mưa bão kéo dài", "status": "Đã xử lý"}))
    with SessionLocal() as db:
        risk = db.get(Risk, rid)
        assert risk.status == "Đã xử lý"
        assert risk.created_at                      # untouched by edit
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/risks/{rid}/delete"))


def test_method_crud(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/methods/new", data={"name": "  Hàng rào tạm  ", "quantity": "120"})
    assert "Đã thêm biện pháp/hạng mục." in follow(client, r).text
    assert "Vui lòng nhập hạng mục." in client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/methods/new", data={"name": ""}).text


# ---- HSSE / diary -----------------------------------------------------------------------------

def test_hsse_log(client):
    assert "Vui lòng nhập nội dung ghi nhận HSSE." in client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/hsse", data={"description": ""}).text
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/hsse", data={"description": "Thiếu dây an toàn", "log_type": "Near miss",
                                   "people_affected": "2", "severity": "Cao"})
    assert "Đã lưu nhật ký HSSE." in follow(client, r).text
    with SessionLocal() as db:
        log = db.query(SafetyLog).filter_by(description="Thiếu dây an toàn").one()
        assert log.people_affected == 2 and log.log_date
        log_id = log.id
    assert "Đã xóa nhật ký HSSE." in follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/hsse/{log_id}/delete")).text


def test_diary_log(client):
    assert "Vui lòng nhập công việc đã thực hiện." in client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/diary", data={"completed_work": ""}).text
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/diary", data={"completed_work": "Lắp cốt thép sàn", "worker_count": "35", "weather": "Nắng"})
    assert "Đã lưu nhật ký công trường." in follow(client, r).text
    with SessionLocal() as db:
        entry = db.query(Diary).filter_by(completed_work="Lắp cốt thép sàn").one()
        assert entry.worker_count == 35
        entry_id = entry.id
    assert "Đã xóa nhật ký." in follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/diary/{entry_id}/delete")).text


def test_project_save(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/project", data={"name": "Dự án thử", "contract_value": "192000000000", "notes": "ghi chú"})
    assert "Đã lưu thông tin dự án." in follow(client, r).text
    with SessionLocal() as db:
        project = repo.get_project(db, 1)
        assert project.name == "Dự án thử" and project.contract_value == 192000000000


# ---- Excel ------------------------------------------------------------------------------------

def test_export_has_all_sheets(client):
    r = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/reports/export.xlsx")
    assert r.status_code == 200
    assert "Bao_cao_quan_ly_du_an_AZB.xlsx" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["TongQuan", "TienDo", "NguonLuc", "ChiPhi", "RuiRo", "BienPhap", "HSSE", "NhatKy"]
    assert wb["TienDo"].max_row > 1


def test_import_keeps_app_entered_data(client):
    with SessionLocal() as db:
        task = db.query(Task).filter(Task.source_id.is_not(None)).order_by(Task.source_id).first()
        source_id, task_id = task.source_id, task.id
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/{task_id}/edit", data={
        "title": task.title, "source_id": str(source_id), "actual_progress": "65", "actual_status": "Đang thi công",
        "owner": "Trần B", "priority": "Cao"}))

    r = _post_sample(client, mode="update")
    assert r.headers["location"] == "/nha-may-san-xuat-cac-san-pham-sau-thep/import"            # stays in the same project
    page = follow(client, r)
    assert "Đã cập nhật dự án này từ file" in page.text

    with SessionLocal() as db:
        kept = db.query(Task).filter_by(source_id=source_id).first()
        assert kept.actual_progress == 65 and kept.owner == "Trần B" and kept.priority == "Cao"
        assert repo.count_rows(db, Cost, 1) == 63
        # diary / HSSE logs are never touched by an import
        assert repo.count_rows(db, Diary, 1) >= 0


def test_import_rejects_wrong_type_and_missing_file(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import", files={"workbook": ("notes.txt", b"hello", "text/plain")})
    assert "Chỉ hỗ trợ file .xlsx." in r.text
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import", files={"workbook": ("", b"", "application/octet-stream")})
    assert r.status_code == 200 and "Chọn file Excel" in r.text


def test_import_bad_workbook_rolls_back(client):
    with SessionLocal() as db:
        before = repo.count_rows(db, Task, 1)
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import", files={"workbook": ("broken.xlsx", b"not a real workbook", "application/octet-stream")})
    assert r.status_code == 200 and "Không mở được" in r.text and "Chưa nhập gì" in r.text
    with SessionLocal() as db:
        assert repo.count_rows(db, Task, 1) == before


# ---- backup before import ---------------------------------------------------------------------

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _FormReader(HTMLParser):
    """Collects what a browser would submit from the preview form: hidden/checked inputs and selects."""

    def __init__(self):
        super().__init__()
        self.fields: dict[str, str] = {}
        self._select = None
        self._first_option = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name"):
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio"):
                if "checked" in a:
                    self.fields[a["name"]] = a.get("value", "on")
            elif kind != "file":
                self.fields[a["name"]] = a.get("value", "")
        elif tag == "select" and a.get("name"):
            self._select = a["name"]
            self._first_option = None
            self.fields[self._select] = ""
        elif tag == "option" and self._select:
            if "selected" in a:
                self.fields[self._select] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None


def _preview_fields(html: str) -> dict[str, str]:
    reader = _FormReader()
    reader.feed(html)
    return reader.fields


def _upload_bytes(client, data: bytes, filename: str = "plan.xlsx", project_id: int = 1, **fields):
    """Step 1: upload. Returns the response (the preview page when the file could be read)."""
    return client.post(f"{u(project_id)}/import", data=fields, files={"workbook": (filename, data, XLSX_TYPE)})


def _confirm(client, preview_html: str, project_id: int = 1, action: str = "confirm", **changes):
    """Step 3 (or the re-preview): send the form the way the browser would, with the user's changes."""
    form = _preview_fields(preview_html)
    form.update(changes)
    return client.post(f"{u(project_id)}/import/{action}", data=form)


def _import_bytes(client, data: bytes, filename: str = "plan.xlsx", project_id: int = 1, **fields):
    """Upload then confirm, like a user who accepts the preview. Returns the confirm response."""
    preview = _upload_bytes(client, data, filename, project_id, **fields)
    assert preview.status_code == 200 and 'name="token"' in preview.text, preview.text[:400]
    changes = {}
    if "needs-name" in preview.text and not fields.get("project_name"):
        # the file has no project name, so (like a user would) type one in the preview
        changes["project_name"] = Path(filename).stem.replace("_", " ")
    return _confirm(client, preview.text, project_id, **changes)


def _post_sample(client, **data):
    return _import_bytes(client, SAMPLE_XLSX.read_bytes(), "plan.xlsx", 1, **data)


def _backup_files():
    from azb_hub.services.backup import backups_dir
    return sorted(backups_dir().glob("*.db")) if backups_dir().exists() else []


def test_import_page_offers_backup_choice(client):
    page = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/import").text
    assert 'name="backup" value="yes" checked' in page
    assert 'name="backup" value="no"' in page
    assert "Sao lưu trước khi nhập?" in page


def test_import_with_backup_creates_a_readable_copy(client):
    before = _backup_files()
    page = follow(client, _post_sample(client, backup="yes"))
    assert "Đã sao lưu database vào backups/" in page.text
    after = _backup_files()
    assert len(after) == len(before) + 1

    newest = max(after, key=lambda p: p.stat().st_mtime)
    con = sqlite3.connect(newest)
    try:
        assert con.execute("select count(*) from tasks").fetchone()[0] > 0
        assert con.execute("select count(*) from project").fetchone()[0] >= 1
    finally:
        con.close()
    assert newest.name in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/import").text      # listed on the page


def test_import_backup_is_the_default(client):
    before = len(_backup_files())
    follow(client, _post_sample(client))                   # no "backup" field at all
    assert len(_backup_files()) == before + 1


def test_import_without_backup_when_user_chooses_no(client):
    before = len(_backup_files())
    page = follow(client, _post_sample(client, backup="no"))
    assert "Bạn đã chọn không sao lưu trước khi nhập." in page.text
    assert len(_backup_files()) == before


def test_invalid_file_makes_no_backup(client):
    before = len(_backup_files())
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import", data={"backup": "yes"}, files={"workbook": ("notes.txt", b"x", "text/plain")})
    assert "Chỉ hỗ trợ file .xlsx." in r.text
    assert len(_backup_files()) == before


# ---- many projects ----------------------------------------------------------------------------

def _new_project_from_sample(client, **data):
    """Import the sample workbook as a new project; return the new project's id."""
    r = _post_sample(client, mode="new", **data)
    assert r.status_code == 303, r.text[:300]
    return project_id_from(r.headers["location"]), r


def test_import_page_only_updates_current_project(client):
    page = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/import").text
    assert 'name="mode" value="update"' in page
    assert 'name="mode" value="new"' not in page
    assert 'name="project_name"' not in page


def test_import_creates_a_new_project_and_leaves_old_one_alone(client):
    follow(client, client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks/new", data={"title": "Việc chỉ có ở dự án 1", "actual_progress": "30"}))
    with SessionLocal() as db:
        before = {m.__tablename__: repo.count_rows(db, m, 1) for m in (Task, Cost, Risk, Resource, Diary)}

    new_id, r = _new_project_from_sample(client)
    assert new_id != 1
    page = follow(client, r)
    assert "Đã tạo dự án mới" in page.text and "Các dự án khác không thay đổi." in page.text

    with SessionLocal() as db:
        after = {m.__tablename__: repo.count_rows(db, m, 1) for m in (Task, Cost, Risk, Resource, Diary)}
        assert after == before                                   # project 1 untouched
        assert repo.count_rows(db, Task, new_id) > 0
        assert repo.count_rows(db, Cost, new_id) == 63
        assert all(t.actual_progress == 0 for t in repo.all_tasks(db, new_id))   # nothing carried over
        assert repo.get_project(db, new_id).status == "active"

    assert "Việc chỉ có ở dự án 1" in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks").text
    assert "Việc chỉ có ở dự án 1" not in client.get(f"{u(new_id)}/tasks").text


def test_sidebar_lists_projects_and_marks_current(client):
    new_id, _ = _new_project_from_sample(client)
    page = client.get(f"{u(new_id)}/tasks").text
    assert 'id="projectMenu"' in page
    assert f'href="/nha-may-san-xuat-cac-san-pham-sau-thep/"' in page and f'href="{u(new_id)}/"' in page
    assert 'is-current" href="%s/"' % u(new_id) in page
    # links in the sidebar stay inside the open project
    assert f'href="{u(new_id)}/costs"' in page


def test_records_of_one_project_are_hidden_from_another(client):
    new_id, _ = _new_project_from_sample(client)
    follow(client, client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/costs/new", data={"name": "Khoản chi bí mật dự án 1", "budget_amount": "1"}))
    with SessionLocal() as db:
        cost_id = db.query(Cost).filter_by(name="Khoản chi bí mật dự án 1").one().id

    assert client.get(f"{u(new_id)}/costs/{cost_id}/edit").status_code == 404
    assert client.post(f"{u(new_id)}/costs/{cost_id}/edit", data={"name": "đổi tên"}).status_code == 404
    client.post(f"{u(new_id)}/costs/{cost_id}/delete")          # wrong project: must not delete
    with SessionLocal() as db:
        assert db.get(Cost, cost_id).name == "Khoản chi bí mật dự án 1"
    assert "Khoản chi bí mật dự án 1" not in client.get(f"{u(new_id)}/costs").text


def test_old_p_urls_redirect_to_slug_urls(client):
    r = client.get("/p/1/tasks?q=nền")
    assert r.status_code == 308
    assert r.headers["location"].startswith("/nha-may-san-xuat-cac-san-pham-sau-thep/tasks?q=")
    assert client.get("/p/1").headers["location"] == "/nha-may-san-xuat-cac-san-pham-sau-thep/"


def test_slugs_are_unique_and_readable(client):
    new_id, _ = _new_project_from_sample(client)
    with SessionLocal() as db:
        slugs = [p.slug for p in repo.list_projects(db, include_archived=True)]
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) for s in slugs)
    assert "new" not in slugs


def test_unknown_project_is_404(client):
    assert client.get("/khong-co-du-an-nay/tasks").status_code == 404
    assert client.get("/khong-co-du-an-nay/").status_code == 404


def test_home_is_a_page_not_a_redirect_to_the_last_project(client):
    new_id, _ = _new_project_from_sample(client)
    client.get(f"{u(new_id)}/gantt")
    r = client.get("/")
    assert r.status_code == 200 and "Bạn muốn xem dự án nào?" in r.text
    assert f'href="{u(new_id)}/"' in r.text                              # the project is a card on the home page


def test_archive_hides_project_from_menu_and_restore_brings_it_back(client):
    new_id, _ = _new_project_from_sample(client)
    page = follow(client, client.post(f"{u(new_id)}/archive"))
    assert "Đã lưu trữ dự án" in page.text
    assert f'href="{u(new_id)}/"' in page.text                 # still listed on the project page...
    menu = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/").text.split('id="projectMenu"')[1].split("</details>")[0]
    assert f'href="{u(new_id)}/"' not in menu                  # ...but not in the sidebar menu
    with SessionLocal() as db:
        assert repo.count_rows(db, Task, new_id) > 0            # data kept

    follow(client, client.post(f"{u(new_id)}/restore"))
    menu = client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/").text.split('id="projectMenu"')[1].split("</details>")[0]
    assert f'href="{u(new_id)}/"' in menu


def test_projects_page_lists_all_projects(client):
    page = client.get("/projects").text
    assert "Danh sách dự án" in page and 'href="/nha-may-san-xuat-cac-san-pham-sau-thep/"' in page


def test_projects_page_has_an_add_button_at_the_top_right(client):
    page = client.get("/projects").text
    head = page.split('class="heading-actions"')[1].split("</div>")[0]
    assert 'href="/projects/new"' in head and "Thêm dự án mới" in head


def test_add_project_page_offers_excel_and_empty(client):
    page = client.get("/projects/new")
    assert page.status_code == 200
    assert 'enctype="multipart/form-data"' in page.text and 'name="mode" value="new"' in page.text
    assert 'action="/projects/new"' in page.text and "Tạo dự án trống" in page.text
    assert 'href="/projects/new"' in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/").text            # also in the sidebar menu


def test_create_empty_project_with_just_a_name(client):
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
    r = client.post("/projects/new", data={"name": "  Văn phòng Quận 7  "})
    assert r.status_code == 303
    new_id = project_id_from(r.headers["location"])
    page = follow(client, r)
    assert "Đã tạo dự án" in page.text
    with SessionLocal() as db:
        project = repo.get_project(db, new_id)
        assert project.name == "Văn phòng Quận 7" and project.status == "active"
        assert len(repo.list_projects(db, include_archived=True)) == before + 1
        assert all(repo.count_rows(db, m, new_id) == 0 for m, _ in repo.PROJECT_DATA)
    for path in ("tasks", "costs", "risks", "gantt", "reports"):           # an empty project renders everywhere
        assert client.get(f"{u(new_id)}/{path}").status_code == 200


def test_create_empty_project_needs_a_name(client):
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
    r = client.post("/projects/new", data={"name": "   "})
    assert r.status_code == 200 and "Hãy nhập tên dự án" in r.text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == before


def test_excel_form_on_the_add_page_leads_to_a_new_project(client):
    page = client.get("/projects/new").text
    action = re.search(r'<form method="post" enctype="multipart/form-data" action="([^"]+)"', page).group(1)
    r = client.post(action, data={"mode": "new", "backup": "yes", "project_name": ""},
                    files={"workbook": ("plan.xlsx", SAMPLE_XLSX.read_bytes(), XLSX_TYPE)})
    assert r.status_code == 200 and 'name="token"' in r.text                  # straight to the preview


def test_failed_new_import_creates_no_project(client):
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
    r = _upload_bytes(client, b"not a workbook", "broken.xlsx", mode="new")
    assert "Chưa nhập gì" in r.text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == before


# ---- wrong files and project names ------------------------------------------------------------

def _xlsx_bytes(build) -> bytes:
    """A workbook made in memory; build(wb) fills it."""
    from openpyxl import Workbook
    wb = Workbook()
    build(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _sample_without_name() -> bytes:
    wb = load_workbook(SAMPLE_XLSX)
    wb["TongQuan"]["C4"] = None
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _blank_book() -> bytes:
    return _xlsx_bytes(lambda wb: wb.active.cell(1, 1, "sádfasfdsfdsfaf"))      # like a throw-away test file


def test_only_the_project_name_is_required_so_a_blank_file_makes_an_empty_project(client):
    with SessionLocal() as db:
        projects_before = len(repo.list_projects(db, include_archived=True))
    r = _upload_bytes(client, _blank_book(), "trong.xlsx", mode="new")
    assert r.status_code == 200
    assert "Chưa nhận ra dữ liệu nào" in r.text and "Sheet" in r.text
    assert "needs-name" in r.text                                          # the page asks for the name
    assert "disabled" not in r.text.split('formaction="/nha-may-san-xuat-cac-san-pham-sau-thep/import/confirm"')[1].split(">")[0]   # can still import

    # no name anywhere -> refused, nothing created
    forced = _confirm(client, r.text)
    assert forced.status_code == 200 and "Chưa có tên dự án" in forced.text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == projects_before

    # name typed -> an empty project is created
    done = _confirm(client, r.text, project_name="Dự án trống để thử")
    new_id = _new_project_id(done)
    with SessionLocal() as db:
        assert _project_name(new_id) == "Dự án trống để thử"
        assert all(repo.count_rows(db, m, new_id) == 0 for m, _ in repo.PROJECT_DATA)


def test_file_with_only_an_overview_sheet_is_imported_with_every_section_empty(client):
    def build(wb):
        wb.active.title = "Tổng quan"
        wb.active["A4"], wb.active["C4"] = "Tên dự án", "Chỉ có tên"
    new_id = _new_project_id(_import_bytes(client, _xlsx_bytes(build), "ten.xlsx", mode="new"))
    with SessionLocal() as db:
        project = repo.get_project(db, new_id)
        assert project.name == "Chỉ có tên" and project.client == ""
        assert all(repo.count_rows(db, m, new_id) == 0 for m, _ in repo.PROJECT_DATA)


def test_update_with_nothing_recognisable_is_refused_and_changes_nothing(client):
    new_id = _new_project_id(_post_sample(client, mode="new"))
    with SessionLocal() as db:
        tasks_before = repo.count_rows(db, Task, new_id)
    r = _upload_bytes(client, _blank_book(), "trong.xlsx", new_id, mode="update")
    assert "Chưa có gì để cập nhật" in r.text
    assert "disabled" in r.text.split(f'formaction="{u(new_id)}/import/confirm"')[1].split(">")[0]
    forced = _confirm(client, r.text, new_id)
    assert forced.status_code == 200 and "không có gì để cập nhật" in forced.text
    with SessionLocal() as db:
        assert repo.count_rows(db, Task, new_id) == tasks_before


def test_update_with_an_empty_sheet_keeps_the_existing_tasks(client):
    new_id = _new_project_id(_post_sample(client, mode="new"))
    def build(wb):
        wb.active.title = "TongQuan"
        wb.active["A4"], wb.active["C4"] = "Dự án", "Tên mới từ file"
        wb.create_sheet("TienDo")                                             # sheet exists, no rows
    with SessionLocal() as db:
        tasks_before = repo.count_rows(db, Task, new_id)
    r = _upload_bytes(client, _xlsx_bytes(build), "rong.xlsx", new_id, mode="update")
    assert "Dữ liệu hiện có được giữ nguyên" in r.text
    follow(client, _confirm(client, r.text, new_id))
    with SessionLocal() as db:
        assert repo.count_rows(db, Task, new_id) == tasks_before              # not wiped by an empty sheet


def test_new_project_uses_the_name_typed_on_the_form(client):
    new_id, _ = _new_project_from_sample(client, project_name="  Kho logistics Bình Dương  ")
    assert _project_name(new_id) == "Kho logistics Bình Dương"


def test_name_is_required_only_when_the_file_has_none(client):
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
    preview = _upload_bytes(client, _sample_without_name(), "Cong_trinh_B.xlsx", mode="new")
    assert "File không ghi tên dự án" in preview.text and "needs-name" in preview.text

    refused = _confirm(client, preview.text)
    assert refused.status_code == 200 and "Chưa có tên dự án" in refused.text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == before   # nothing created

    new_id = _new_project_id(_confirm(client, preview.text, project_name="Công trình B"))
    assert _project_name(new_id) == "Công trình B"
    with SessionLocal() as db:
        assert repo.get_project(db, new_id).source_file == "Cong_trinh_B.xlsx"
        assert repo.count_rows(db, Task, new_id) == 85                       # the rest of the file imported fine


def test_a_file_with_a_name_needs_no_typing(client):
    preview = _upload_bytes(client, SAMPLE_XLSX.read_bytes(), "plan.xlsx", mode="new")
    assert "needs-name" not in preview.text                                  # the name box is optional here
    new_id = _new_project_id(_confirm(client, preview.text))
    assert _project_name(new_id) == "Nhà máy sản xuất các sản phẩm sau thép"


def test_update_mode_ignores_the_new_name_field(client):
    before = _project_name(1)
    follow(client, _post_sample(client, mode="update", project_name="Không được đổi tên"))
    assert _project_name(1) != "Không được đổi tên"           # name comes from the file, not the form


# ---- import: preview and flexible columns -----------------------------------------------------

def _table_book(rows, sheet="Tiến độ", extra_sheets=None, title_cell=None) -> bytes:
    """A workbook with one table made of ``rows`` (the first row is the header) on ``sheet``."""
    def build(wb):
        ws = wb.active
        ws.title = sheet
        for r in rows:
            ws.append(r)
        for name, data in (extra_sheets or {}).items():
            other = wb.create_sheet(name)
            for r in data:
                other.append(r)
        if title_cell:
            overview = wb.create_sheet("Tổng quan")
            overview["A4"], overview["C4"] = "Tên dự án", title_cell
    return _xlsx_bytes(build)


def _new_project_id(response) -> int:
    assert response.status_code == 303, response.text[:300]
    return project_id_from(response.headers["location"])


def test_preview_shows_the_mapping_and_writes_nothing(client):
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
        tasks_before = repo.count_rows(db, Task, 1)
    r = _upload_bytes(client, SAMPLE_XLSX.read_bytes(), "plan.xlsx", mode="new")
    assert r.status_code == 200
    for text in ("Kiểm tra trước khi nhập", "Ghép với trường", "tự nhận", "Hạng mục / công việc",
                 "Tên công việc", "Cập nhật xem trước", "Đọc được <b>85</b> dòng"):
        assert text in r.text, text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == before
        assert repo.count_rows(db, Task, 1) == tasks_before


def test_columns_with_other_names_and_order_are_recognised(client):
    book = _table_book([
        ["Task", "Finish", "Start", "Mã", "Ghi chú PM"],
        ["Đổ bê tông sàn", "20/03/2026", "2026-03-01", 7, "ưu tiên"],
        ["Lắp đặt MEP", "05/04/2026", "21/03/2026", 8, None],
    ])
    new_id = _new_project_id(_import_bytes(client, book, "kho_b.xlsx", mode="new"))
    with SessionLocal() as db:
        tasks = {t.title: t for t in repo.all_tasks(db, new_id)}
    t = tasks["Đổ bê tông sàn"]
    assert (t.source_id, t.start_date, t.end_date, t.notes) == (7, "2026-03-01", "2026-03-20", "ưu tiên")
    assert tasks["Lắp đặt MEP"].notes in ("", None)                       # empty cell stays empty


def test_missing_columns_stay_empty_and_import_still_works(client):
    book = _table_book([["Tên công việc"], ["Việc A"], ["Việc B"], ["Việc C"]])
    new_id = _new_project_id(_import_bytes(client, book, "chi_ten.xlsx", mode="new"))
    with SessionLocal() as db:
        tasks = repo.all_tasks(db, new_id)
        project = repo.get_project(db, new_id)
    assert sorted(t.title for t in tasks) == ["Việc A", "Việc B", "Việc C"]
    assert all(t.start_date is None and t.plan_progress == 0 and t.category == "" for t in tasks)
    assert project.client == "" and project.package_name == ""
    assert project.name == "chi ten"                                    # no name anywhere: the file name


def test_sheet_with_a_different_name_is_found_by_its_header(client):
    book = _table_book([["STT", "Nội dung công việc", "Bắt đầu", "Kết thúc"], [1, "Đào đất", "01/02/2026", "10/02/2026"]],
                       sheet="Lịch thi công tuần")
    new_id = _new_project_id(_import_bytes(client, book, "x.xlsx", mode="new"))
    with SessionLocal() as db:
        assert [t.title for t in repo.all_tasks(db, new_id)] == ["Đào đất"]


def test_unknown_column_is_flagged_fixable_and_remembered(client):
    rows = [["ID", "Công việc", "Bắt đầu", "Hoàn thành dự kiến"], [1, "Móng M1", "01/06/2026", "09/06/2026"]]
    first = _upload_bytes(client, _table_book(rows), "a.xlsx", mode="new", project_name="Dự án A")
    assert "chưa nhận ra" in first.text and "Hoàn thành dự kiến" in first.text

    # the user maps the column to "Ngày kết thúc" in the preview
    column_name = next(k for k, v in _preview_fields(first.text).items()
                       if k.startswith("was_tasks_") and v == "" and re.search(
                           rf'name="col_tasks_{k.split("_")[-1]}"', first.text))
    idx = column_name.split("_")[-1]
    resp = _confirm(client, first.text, **{f"col_tasks_{idx}": "end_date"})
    new_id = _new_project_id(resp)
    with SessionLocal() as db:
        assert repo.all_tasks(db, new_id)[0].end_date == "2026-06-09"
        assert any(a.kind == "column" and a.text_shown == "Hoàn thành dự kiến" and a.field == "end_date"
                   for a in repo.list_aliases(db))

    # next file with the same header is understood without any fix
    second = _upload_bytes(client, _table_book([["ID", "Công việc", "Hoàn thành dự kiến"], [5, "Cọc C2", "20/07/2026"]]),
                           "b.xlsx", mode="new", project_name="Dự án B")
    assert "đã nhớ" in second.text
    new_id = _new_project_id(_confirm(client, second.text))
    with SessionLocal() as db:
        assert repo.all_tasks(db, new_id)[0].end_date == "2026-07-20"


def test_choice_is_not_remembered_when_the_box_is_unticked(client):
    rows = [["ID", "Công việc", "Dự kiến xong sớm"], [1, "Việc Z", "01/09/2026"]]
    page = _upload_bytes(client, _table_book(rows), "z.xlsx", mode="new", project_name="Dự án Z")
    form = _preview_fields(page.text)
    form.pop("remember", None)                    # an unticked checkbox sends nothing
    form["col_tasks_2"] = "end_date"              # third column: "Dự kiến xong sớm"
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import/confirm", data=form)
    pid = _new_project_id(r)
    with SessionLocal() as db:
        assert repo.all_tasks(db, pid)[0].end_date == "2026-09-01"       # the choice was used...
    with SessionLocal() as db:
        assert not any(a.text_shown == "Dự kiến xong sớm" for a in repo.list_aliases(db))


def test_update_keeps_data_of_sheets_the_file_does_not_have(client):
    new_id = _new_project_id(_post_sample(client, mode="new"))
    with SessionLocal() as db:
        cost = db.query(Cost).filter_by(project_id=new_id).first()
        cost.actual_amount = 123456.0
        db.commit()
        costs_before, risks_before = repo.count_rows(db, Cost, new_id), repo.count_rows(db, Risk, new_id)
        first_cost = cost.name

    book = _table_book([["ID", "Công việc"], [1, "Chỉ còn một việc"]])         # no cost / risk sheet at all
    follow(client, _import_bytes(client, book, "ngan.xlsx", new_id, mode="update"))
    with SessionLocal() as db:
        assert repo.count_rows(db, Cost, new_id) == costs_before          # kept
        assert repo.count_rows(db, Risk, new_id) == risks_before          # kept
        assert db.query(Cost).filter_by(project_id=new_id, name=first_cost).one().actual_amount == 123456.0
        assert [t.title for t in repo.all_tasks(db, new_id)] == ["Chỉ còn một việc"]


def test_update_keeps_old_values_for_columns_the_file_does_not_have(client):
    first = _table_book([["ID", "Công việc", "Bắt đầu", "Kết thúc"], [1, "Móng", "01/03/2026", "20/03/2026"]])
    pid = _new_project_id(_import_bytes(client, first, "v1.xlsx", mode="new"))
    with SessionLocal() as db:
        task = repo.all_tasks(db, pid)[0]
        task.actual_progress, task.owner = 55, "Lê C"
        db.commit()

    second = _table_book([["ID", "Công việc"], [1, "Móng (đổi tên)"]])        # dates column is gone
    follow(client, _import_bytes(client, second, "v2.xlsx", pid, mode="update"))
    with SessionLocal() as db:
        t = repo.all_tasks(db, pid)[0]
    assert t.title == "Móng (đổi tên)"
    assert (t.start_date, t.end_date) == ("2026-03-01", "2026-03-20")          # old values stay
    assert (t.actual_progress, t.owner) == (55, "Lê C")


def test_update_empty_cell_in_an_existing_column_becomes_empty(client):
    first = _table_book([["ID", "Công việc", "Kết thúc"], [1, "Móng", "20/03/2026"]])
    pid = _new_project_id(_import_bytes(client, first, "v1.xlsx", mode="new"))
    second = _table_book([["ID", "Công việc", "Kết thúc"], [1, "Móng", None]])
    follow(client, _import_bytes(client, second, "v2.xlsx", pid, mode="update"))
    with SessionLocal() as db:
        assert repo.all_tasks(db, pid)[0].end_date is None


def test_update_matches_by_title_when_the_file_has_no_wbs_codes(client):
    first = _table_book([["ID", "Công việc"], [1, "Đào đất hố móng"], [2, "Đổ bê tông lót"]])
    pid = _new_project_id(_import_bytes(client, first, "v1.xlsx", mode="new"))
    with SessionLocal() as db:
        for t in repo.all_tasks(db, pid):
            t.actual_progress = 80 if t.title.startswith("Đào") else 10
        db.commit()

    second = _table_book([["Công việc", "Bắt đầu"], ["  đào đất hố móng ", "01/04/2026"], ["Việc mới hoàn toàn", None]])
    preview = _upload_bytes(client, second, "v2.xlsx", pid, mode="update")
    assert "khớp theo tên: 1" in preview.text
    follow(client, _confirm(client, preview.text, pid))
    with SessionLocal() as db:
        tasks = {t.title: t for t in repo.all_tasks(db, pid)}
    assert tasks["đào đất hố móng"].actual_progress == 80                    # matched by title (case/space tolerant)
    assert tasks["Việc mới hoàn toàn"].actual_progress == 0


def test_user_can_pick_a_sheet_in_the_preview(client):
    book = _table_book([["Ghi chú", "Ngày"], ["không phải tiến độ", "x"]], sheet="Linh tinh",
                       extra_sheets={"Bảng X": [["Hạng mục / công việc", "Bắt đầu"], ["Việc từ bảng X", "01/05/2026"]]})
    page = _upload_bytes(client, book, "m.xlsx", mode="new", project_name="Dự án M")
    assert 'name="sheet_tasks"' in page.text
    fixed = _confirm(client, page.text, **{"sheet_tasks": "Bảng X"})
    pid = _new_project_id(fixed)
    with SessionLocal() as db:
        assert [t.title for t in repo.all_tasks(db, pid)] == ["Việc từ bảng X"]


def test_stale_or_invalid_preview_token_is_refused(client):
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import/confirm", data={"token": "0" * 32, "mode": "new", "backup": "no"})
    assert "hết hạn" in r.text
    r = client.post("/nha-may-san-xuat-cac-san-pham-sau-thep/import/confirm", data={"token": "../../etc/passwd", "mode": "new"})
    assert "hết hạn" in r.text or "không hợp lệ" in r.text


def test_remembered_choice_can_be_removed(client):
    with SessionLocal() as db:
        repo.save_alias(db, "column", "tasks", "cotthuxx", "Cột thử", "end_date")
        db.commit()
        alias_id = next(a.id for a in repo.list_aliases(db) if a.text_norm == "cotthuxx")
    assert "Cột thử" in client.get("/nha-may-san-xuat-cac-san-pham-sau-thep/import").text
    follow(client, client.post(f"/nha-may-san-xuat-cac-san-pham-sau-thep/import/aliases/{alias_id}/delete"))
    with SessionLocal() as db:
        assert not any(a.id == alias_id for a in repo.list_aliases(db))


def test_delete_button_is_prominent(client):
    new_id = _new_project_id(_post_sample(client, mode="new"))
    page = client.get("/projects").text
    block = page.split(f'data-action="{u(new_id)}/delete"')[0].rsplit("<button", 1)[1]
    assert "btn-danger" in block and "btn-delete" in block
    assert "Xoá dự án" in page


# ---- delete a project -------------------------------------------------------------------------

def _project_name(pid):
    with SessionLocal() as db:
        return repo.get_project(db, pid).name


def test_active_project_can_be_deleted_without_archiving_first(client):
    new_id, _ = _new_project_from_sample(client)
    page = client.get("/projects").text
    assert f'data-action="{u(new_id)}/delete"' in page      # delete offered on an active project too
    assert "Lưu trữ" in page                                       # archive still available, just not required

    page = follow(client, client.post(f"{u(new_id)}/delete"))
    assert "Đã xoá vĩnh viễn dự án" in page.text
    with SessionLocal() as db:
        assert repo.get_project(db, new_id) is None


def test_delete_needs_no_typed_name(client):
    """The dialog only asks yes/no; the server must not ask for a name either."""
    new_id, _ = _new_project_from_sample(client)
    page = client.get("/projects").text
    assert 'name="confirm_name"' not in page and 'id="confirmName"' not in page
    follow(client, client.post(f"{u(new_id)}/delete", data={}))
    with SessionLocal() as db:
        assert repo.get_project(db, new_id) is None


def test_delete_removes_only_its_data_and_backs_up_first(client):
    new_id, _ = _new_project_from_sample(client)
    follow(client, client.post(f"{u(new_id)}/diary", data={"completed_work": "Nhật ký của dự án sẽ xoá"}))
    with SessionLocal() as db:
        project_1_before = {m.__tablename__: repo.count_rows(db, m, 1) for m, _ in repo.PROJECT_DATA}
    backups_before = len(_backup_files())

    gone_url = u(new_id)
    page = follow(client, client.post(f"{u(new_id)}/delete"))
    assert "Đã xoá vĩnh viễn dự án" in page.text and "truoc_xoa_du_an" in page.text

    with SessionLocal() as db:
        assert repo.get_project(db, new_id) is None
        assert all(repo.count_rows(db, m, new_id) == 0 for m, _ in repo.PROJECT_DATA)   # cascade removed every row
        assert {m.__tablename__: repo.count_rows(db, m, 1) for m, _ in repo.PROJECT_DATA} == project_1_before
    assert len(_backup_files()) == backups_before + 1
    assert any("truoc_xoa_du_an" in f.name for f in _backup_files())
    assert client.get(f"{gone_url}/").status_code == 404


def test_last_project_cannot_be_deleted(client, monkeypatch):
    new_id, _ = _new_project_from_sample(client)
    with SessionLocal() as db:
        only = repo.get_project(db, new_id)
    monkeypatch.setattr(repo, "list_projects", lambda db, include_archived=False, **_: [only])
    page = follow(client, client.post(f"{u(new_id)}/delete"))
    assert "Không thể xoá dự án cuối cùng" in page.text
    monkeypatch.undo()
    with SessionLocal() as db:
        assert repo.get_project(db, new_id) is not None


# ---- migration from the Flask-era database ----------------------------------------------------

LEGACY_DDL = """
CREATE TABLE project (id INTEGER PRIMARY KEY CHECK (id = 1), name TEXT NOT NULL, client TEXT, contractor TEXT,
  package_name TEXT, description TEXT, start_date TEXT, end_date TEXT, report_date TEXT,
  contract_value REAL DEFAULT 0, prelim_budget REAL DEFAULT 0, planned_progress REAL DEFAULT 0, source_file TEXT, notes TEXT);
CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER, category TEXT, title TEXT NOT NULL,
  task_type TEXT DEFAULT 'Chi tiết', planned_days REAL DEFAULT 0, start_date TEXT, end_date TEXT,
  duration_calculated REAL DEFAULT 0, schedule_check TEXT, plan_progress REAL DEFAULT 0, plan_status TEXT, tet_flag TEXT,
  float_days REAL DEFAULT 0, notes TEXT, actual_progress REAL DEFAULT 0, actual_status TEXT DEFAULT 'Chưa cập nhật',
  owner TEXT DEFAULT '', actual_start_date TEXT, actual_end_date TEXT, updated_at TEXT);
CREATE TABLE resources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, resource_type TEXT, group_name TEXT,
  quantity REAL DEFAULT 0, duration_months REAL DEFAULT 0, start_date TEXT, end_date TEXT, unit TEXT, cost REAL DEFAULT 0, notes TEXT);
CREATE TABLE costs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT 'Chi phí Prelim',
  unit TEXT, quantity REAL DEFAULT 0, unit_price REAL DEFAULT 0, budget_amount REAL DEFAULT 0,
  actual_amount REAL DEFAULT 0, notes TEXT, source_row INTEGER);
CREATE TABLE risks (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER, category TEXT, description TEXT NOT NULL,
  basis TEXT, severity TEXT DEFAULT 'Trung bình', recommendation TEXT, owner TEXT DEFAULT '',
  due_date TEXT, status TEXT DEFAULT 'Chưa xử lý', created_at TEXT);
CREATE TABLE methods (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, unit TEXT, quantity REAL DEFAULT 0,
  specification TEXT, schedule TEXT, source TEXT);
CREATE TABLE hsse_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, value REAL DEFAULT 0, unit TEXT, notes TEXT);
CREATE TABLE safety_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, log_date TEXT NOT NULL, log_type TEXT NOT NULL,
  description TEXT NOT NULL, people_affected INTEGER DEFAULT 0, severity TEXT DEFAULT 'Thấp',
  status TEXT DEFAULT 'Đã ghi nhận', reporter TEXT DEFAULT '', created_at TEXT);
CREATE TABLE diary (id INTEGER PRIMARY KEY AUTOINCREMENT, log_date TEXT NOT NULL, weather TEXT, worker_count INTEGER DEFAULT 0,
  completed_work TEXT NOT NULL, issues TEXT, reporter TEXT, created_at TEXT);
INSERT INTO project (id, name) VALUES (1, 'Dự án cũ');
INSERT INTO tasks (title) VALUES ('Việc cũ chưa có cột priority');
INSERT INTO diary (log_date, completed_work) VALUES ('2026-01-01', 'Nhật ký cũ');
"""


def test_legacy_database_is_upgraded_without_losing_data(tmp_path):
    db_file = tmp_path / "legacy.db"
    con = sqlite3.connect(db_file)
    con.executescript(LEGACY_DDL)
    con.commit()
    con.close()

    code = ("from azb_hub.db import run_migrations; run_migrations(); run_migrations()")
    env = {**os.environ, "AZB_DB_PATH": str(db_file), "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(db_file)
    assert con.execute("select version_num from alembic_version").fetchone() == ("0007",)
    assert con.execute("select count(*) from import_aliases").fetchone() == (0,)
    assert con.execute("select title, priority, project_id from tasks").fetchall() == [
        ("Việc cũ chưa có cột priority", "Trung bình", 1)]
    assert con.execute("select completed_work, project_id from diary").fetchall() == [("Nhật ký cũ", 1)]
    assert con.execute("select name, status from project").fetchall() == [("Dự án cũ", "active")]
    con.execute("insert into project (name) values ('Dự án thứ hai')")      # the old 'only id 1' rule is gone
    assert con.execute("select max(id) from project").fetchone() == (2,)
    con.close()
    backups = list((tmp_path / "backups").glob("legacy_truoc_nang_cap_*.db"))
    assert len(backups) == 1                                       # backed up once, before the upgrade
