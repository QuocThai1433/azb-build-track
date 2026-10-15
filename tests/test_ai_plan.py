"""AI planning from a BOQ + a schedule. Claude is never called: request_plan or the client is replaced."""
import io
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from azb_hub import auth
from azb_hub import repositories as repo
from azb_hub.db import SessionLocal
from azb_hub.models import AuditLog, Cost, Project, Resource, Task
from azb_hub.routers import ai_plan
from azb_hub.services import ai_planner as ap
from azb_hub.services import excel_mapping
from test_app import XLSX_TYPE, _confirm, _preview_fields, _xlsx_bytes, u
from test_auth import _login, _make_user


def _sample_plan(name="Nhà xưởng AI Tân Uyên") -> ap.AiPlan:
    return ap.AiPlan(
        project=ap.AiProject(name=name, client="Công ty Tân Uyên", contractor="AZB"),
        tasks=[ap.AiTask(id=1, wbs="1", title="Phần móng", is_summary=True, planned_days=40,
                         start_date="2026-11-02", end_date="2026-12-11"),
               ap.AiTask(id=2, wbs="1.1", category="Phần móng", title="Đào đất hố móng", is_summary=False,
                         planned_days=10, start_date="2026-11-02", end_date="2026-11-11", quantity=1250.5, unit="m3",
                         boq_refs=["A.1"]),
               ap.AiTask(id=3, wbs="1.2", category="Phần móng", title="Bê tông móng", is_summary=False,
                         planned_days=20, start_date="2026-11-12", end_date="2026-12-11", quantity=420, unit="m3")],
        costs=[ap.AiCost(stt=1, name="Đào đất bằng máy", category="Phần móng", unit="m3", quantity=1250.5,
                         unit_price=85000, budget_amount=106292500),
               ap.AiCost(stt=2, name="Bê tông móng M300", category="Phần móng", unit="m3", quantity=420,
                         unit_price=1650000, budget_amount=693000000)],
        resources=[ap.AiResource(kind="Ban chỉ huy", name="Chỉ huy trưởng", quantity=1, unit="người", duration_months=6),
                   ap.AiResource(kind="Thiết bị", name="Máy đào 0.8m3", quantity=2, unit="máy")],
        methods=[ap.AiMethod(name="Hố móng", unit="m3", quantity=1250, specification="Đào bằng máy")],
        risks=[ap.AiRisk(description="Mưa lớn khi đào móng", severity="Cao", recommendation="Bơm nước hố móng")],
        warnings=["Ngày của công việc 1.2 được suy ra từ thời lượng."])


def _boq_and_schedule():
    def boq(wb):
        ws = wb.active
        ws.title = "BOQ"
        ws.append(["STT", "Nội dung", "ĐVT", "Khối lượng", "Đơn giá", "Thành tiền"])
        ws.append(["A.1", "Đào đất bằng máy", "m3", 1250.5, 85000, 106292500])

    def schedule(wb):
        ws = wb.active
        ws.title = "Tiến độ"
        ws.append(["WBS", "Tên công việc", "Bắt đầu", "Kết thúc"])
        ws.append(["1.1", "Đào đất hố móng", "02/11/2026", "11/11/2026"])
    return _xlsx_bytes(boq), _xlsx_bytes(schedule)


@pytest.fixture()
def ai_on(monkeypatch):
    """Claude configured; the job runs inline and answers with _sample_plan. Returns what Claude was sent."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai_plan, "_start_job", ai_plan._run_job)
    sent = {}

    def fake_request(boq_text, schedule_text, extra="", client=None):
        sent.update(boq=boq_text, schedule=schedule_text, extra=extra)
        return _sample_plan(), {"model": "test", "input_tokens": 10, "output_tokens": 20}
    monkeypatch.setattr(ap, "request_plan", fake_request)
    return sent


def _start(client, boq=None, schedule=None, **fields):
    boq_data, schedule_data = _boq_and_schedule()
    files = {}
    if boq is not False:
        files["boq"] = boq or ("boq.xlsx", boq_data, XLSX_TYPE)
    if schedule is not False:
        files["schedule"] = schedule or ("tiendo.xlsx", schedule_data, XLSX_TYPE)
    return client.post(f"{u(1)}/import/ai", data=fields, files=files)


# ---- the workbook ------------------------------------------------------------------------------

def test_ai_workbook_reads_back_through_the_excel_import(tmp_path):
    path = tmp_path / "ai.xlsx"
    path.write_bytes(ap.build_workbook(_sample_plan()))
    plan = excel_mapping.build_plan(excel_mapping.load_sheets(path), "ai.xlsx", {}, {})
    assert plan.project["name"] == "Nhà xưởng AI Tân Uyên"
    tasks = plan.entities["tasks"].rows
    assert [t["source_id"] for t in tasks] == [1, 2, 3]
    assert tasks[0]["task_type"] == "Tổng hợp" and tasks[1]["task_type"] == "Chi tiết"
    assert tasks[1]["start_date"] == "2026-11-02" and tasks[1]["end_date"] == "2026-11-11"
    assert "KL: 1250.5 m3" in tasks[1]["notes"] and "BOQ: A.1" in tasks[1]["notes"]
    costs = plan.entities["costs"].rows
    assert [(c["name"], c["quantity"], c["budget_amount"]) for c in costs] == [
        ("Đào đất bằng máy", 1250.5, 106292500.0), ("Bê tông móng M300", 420.0, 693000000.0)]
    kinds = sorted(r["resource_type"] for r in plan.entities["resources"].rows)
    assert kinds == ["Ban chỉ huy", "Thiết bị / vận chuyển"]
    assert len(plan.entities["methods"].rows) == 1 and len(plan.entities["risks"].rows) == 1


def test_workbook_text_keeps_row_numbers_and_skips_empty_rows(tmp_path):
    def build(wb):
        ws = wb.active
        ws.title = "BOQ"
        ws.append(["STT", "Nội dung"])
        ws.append([])
        ws.append([1, "Đào đất"])
    path = tmp_path / "boq.xlsx"
    path.write_bytes(_xlsx_bytes(build))
    text = ap.workbook_text(path, "BOQ")
    assert "--- Sheet: BOQ ---" in text
    assert "1\tSTT\tNội dung" in text and "3\t1\tĐào đất" in text
    assert "\n2\t" not in text


# ---- the Claude request ------------------------------------------------------------------------

class _FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def _fake_client(stop_reason="end_turn", parsed=None):
    calls = []

    def stream(**kwargs):
        calls.append(kwargs)
        return _FakeStream(SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, model="claude-opus-5-5",
                                           usage=SimpleNamespace(input_tokens=1, output_tokens=2)))
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    return client, calls


def test_request_plan_sends_both_files_and_the_schema():
    client, calls = _fake_client(parsed=_sample_plan())
    plan, usage = ap.request_plan("BOQ TEXT", "SCHEDULE TEXT", "Khởi công 02/11", client=client)
    assert plan.tasks[1].title == "Đào đất hố móng" and usage["output_tokens"] == 2
    kwargs = calls[0]
    assert kwargs["output_format"] is ap.AiPlan and kwargs["model"] == ap.AI_MODEL
    content = kwargs["messages"][0]["content"]
    assert "BOQ TEXT" in content and "SCHEDULE TEXT" in content and "Khởi công 02/11" in content


@pytest.mark.parametrize("stop_reason, parsed", [("refusal", None), ("max_tokens", None), ("end_turn", None)])
def test_request_plan_turns_bad_answers_into_a_message(stop_reason, parsed):
    client, _calls = _fake_client(stop_reason, parsed)
    with pytest.raises(ap.AiPlanError):
        ap.request_plan("a", "b", client=client)


def test_request_plan_refuses_files_that_are_too_big():
    client, calls = _fake_client(parsed=_sample_plan())
    with pytest.raises(ap.AiPlanError, match="quá lớn"):
        ap.request_plan("x" * ap.MAX_INPUT_CHARS, "y", client=client)
    assert calls == []


# ---- the pages ---------------------------------------------------------------------------------

def test_new_project_page_offers_ai(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    page = client.get("/projects/new").text
    assert "Lập kế hoạch bằng AI" in page and "Chưa cấu hình Claude API" in page
    assert "Chưa cấu hình Claude API" in client.get(f"{u(1)}/import/ai").text


def test_ai_upload_without_key_is_refused(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    r = _start(client)
    assert r.status_code == 200 and "Chưa cấu hình Claude API" in r.text
    assert not list(ai_plan.UPLOAD_DIR.glob("ai_*_boq.xlsx"))


def test_ai_upload_checks_both_files(client, ai_on):
    assert "Chọn file tiến độ" in _start(client, schedule=False).text
    assert "phải là .xlsx" in _start(client, boq=("boq.pdf", b"%PDF", "application/pdf")).text
    assert ai_on == {}


def test_ai_plan_end_to_end_creates_a_project(client, ai_on):
    r = _start(client, extra="Khởi công 02/11/2026")
    assert r.status_code == 303
    job_url = r.headers["location"]
    assert re.search(r"/import/ai/[0-9a-f]{32}$", job_url)
    assert "Đào đất bằng máy" in ai_on["boq"] and "Đào đất hố móng" in ai_on["schedule"]
    assert ai_on["extra"] == "Khởi công 02/11/2026"

    preview = client.get(job_url)
    assert preview.status_code == 200
    assert "Bản nháp do AI lập" in preview.text and "suy ra từ thời lượng" in preview.text
    download = client.get(job_url + "/workbook")
    assert download.status_code == 200 and download.content[:2] == b"PK"

    done = _confirm(client, preview.text)
    assert done.status_code == 303, done.text[:300]
    with SessionLocal() as db:
        project = db.scalar(select(Project).where(Project.name == "Nhà xưởng AI Tân Uyên"))
        assert project is not None
        assert project.client == "Công ty Tân Uyên"
        assert (project.start_date, project.end_date) == ("2026-11-02", "2026-12-11")
        assert repo.count_rows(db, Task, project.id) == 3
        assert repo.count_rows(db, Cost, project.id) == 2
        assert repo.count_rows(db, Resource, project.id) == 2
        actions = set(db.scalars(select(AuditLog.action).where(AuditLog.action.like("ai_plan%"))))
        assert {"ai_plan", "ai_plan_done"} <= actions
        repo.delete_project(db, project.id)      # other test files look tasks up by WBS id across projects
    assert not list(ai_plan.UPLOAD_DIR.glob("ai_*_boq.xlsx"))      # inputs removed after the job


def test_ai_plan_error_is_shown_and_creates_nothing(client, ai_on, monkeypatch):
    def failing(*_a, **_k):
        raise ap.AiPlanError("Claude không xử lý được nội dung hai file này (bị từ chối).")
    monkeypatch.setattr(ap, "request_plan", failing)
    with SessionLocal() as db:
        before = len(repo.list_projects(db, include_archived=True))
    page = client.get(_start(client).headers["location"])
    assert page.status_code == 200 and "bị từ chối" in page.text and "Thử lại" in page.text
    with SessionLocal() as db:
        assert len(repo.list_projects(db, include_archived=True)) == before


def test_ai_job_page_while_running_and_for_unknown_token(client, ai_on, monkeypatch):
    monkeypatch.setattr(ai_plan, "_start_job", lambda *a: None)       # the job never finishes
    page = client.get(_start(client).headers["location"])
    assert "AI đang đọc file" in page.text and 'http-equiv="refresh"' in page.text
    r = client.get(f"{u(1)}/import/ai/{'0' * 32}")
    assert r.status_code == 303 and r.headers["location"].endswith("/import/ai")


def test_staff_cannot_use_ai_planning(client):
    _make_user("nv-ai", auth.NHAN_VIEN, projects={1})
    staff = _login("nv-ai")
    assert staff.get(f"{u(1)}/import/ai").status_code == 403
