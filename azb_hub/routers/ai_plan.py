"""A new project from a bill of quantities + a schedule, planned by Claude.

upload two .xlsx -> a background job asks Claude and writes pending_<token>.xlsx in the AZB layout ->
the wait page reloads until the job ends -> the normal import preview (imports._preview_page), so the
confirm step, backup and audit are the ones of the Excel import. The job state is kept in
instance/uploads/ai_<token>.json; nothing is written to the data tables before the user confirms.
"""
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import audit
from ..constants import MAX_UPLOAD_BYTES
from ..db import get_db
from ..services import ai_planner, excel_import, excel_mapping
from ..web import flash, redirect, render
from . import imports
from .deps import require

router = APIRouter(dependencies=[Depends(require("import.run"))])

UPLOAD_DIR = imports.UPLOAD_DIR
STALE_AFTER = 30 * 60      # a job still "running" after this was lost (server restarted)


def _status_path(token: str) -> Path | None:
    return UPLOAD_DIR / f"ai_{token}.json" if imports.TOKEN.match(token or "") else None


def _read_status(token: str) -> dict[str, Any] | None:
    path = _status_path(token)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_status(token: str, **changes: Any) -> None:
    path = _status_path(token)
    state = _read_status(token) or {}
    state.update(changes)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _run_job(token: str, boq: Path, schedule: Path, extra: str) -> None:
    """Runs in a worker thread. Every outcome ends in the status file."""
    try:
        data, plan, usage = ai_planner.make_plan_workbook(boq, schedule, extra)
        (UPLOAD_DIR / f"pending_{token}.xlsx").write_bytes(data)
        _write_status(token, status="done", warnings=plan.warnings, usage=usage,
                      ai_name=plan.project.name or "", finished=time.time())
    except (ai_planner.AiPlanError, excel_mapping.WorkbookReadError) as exc:
        _write_status(token, status="error", message=str(exc))
    except Exception as exc:          # anything else: show it instead of waiting forever
        _write_status(token, status="error", message=f"Lỗi không mong muốn khi lập kế hoạch: {exc}")
    finally:
        for f in (boq, schedule):
            f.unlink(missing_ok=True)


def _start_job(token: str, boq: Path, schedule: Path, extra: str) -> None:
    threading.Thread(target=_run_job, args=(token, boq, schedule, extra), daemon=True,
                     name=f"ai-plan-{token[:8]}").start()


def _upload_page(request: Request, **ctx: Any):
    return render(request, "ai_plan.html", title="Lập kế hoạch bằng AI", state="upload",
                  ai_enabled=ai_planner.ai_enabled(), ai_model=ai_planner.AI_MODEL, **ctx)


async def _read_xlsx(upload: UploadFile | None, label: str) -> tuple[bytes | None, str | None]:
    if upload is None or not upload.filename:
        return None, f"Chọn file {label} (.xlsx)."
    if not upload.filename.lower().endswith(".xlsx"):
        return None, f"File {label} phải là .xlsx."
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return None, f"File {label} vượt quá giới hạn 20 MB."
    return data, None


@router.get("/import/ai", name="ai_plan_page")
def ai_plan_page(request: Request, project_id: int):
    return _upload_page(request)


@router.post("/import/ai", name="ai_plan_page")
async def ai_plan_start(request: Request, project_id: int, boq: UploadFile | None = File(None),
                        schedule: UploadFile | None = File(None), project_name: Annotated[str, Form()] = "",
                        extra: Annotated[str, Form()] = "", backup: Annotated[str, Form()] = "yes",
                        db: Session = Depends(get_db)):
    ctx = {"typed_name": project_name.strip(), "typed_extra": extra}
    if not ai_planner.ai_enabled():
        flash(request, "Chưa cấu hình Claude API (biến môi trường ANTHROPIC_API_KEY) nên chưa dùng được AI.", "error")
        return _upload_page(request, **ctx)
    boq_data, error = await _read_xlsx(boq, "bảng khối lượng")
    schedule_data, error2 = await _read_xlsx(schedule, "tiến độ")
    if error or error2:
        flash(request, error or error2, "error")
        return _upload_page(request, **ctx)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    imports._cleanup_pending()
    token = secrets.token_hex(16)
    boq_path = UPLOAD_DIR / f"ai_{token}_boq.xlsx"
    schedule_path = UPLOAD_DIR / f"ai_{token}_tiendo.xlsx"
    boq_path.write_bytes(boq_data)
    schedule_path.write_bytes(schedule_data)
    names = [Path(boq.filename).name, Path(schedule.filename).name]
    _write_status(token, status="running", started=time.time(), files=names,
                  project_name=project_name.strip()[:200], backup="no" if backup == "no" else "yes")
    audit.record(db, "ai_plan", "project", None, project_id, new={"files": names, "model": ai_planner.AI_MODEL})
    _start_job(token, boq_path, schedule_path, extra[:2000])
    return redirect(request, "ai_plan_job", project_id=project_id, token=token)


@router.get("/import/ai/{token}", name="ai_plan_job")
def ai_plan_job(request: Request, project_id: int, token: str, db: Session = Depends(get_db)):
    state = _read_status(token)
    if state is None:
        flash(request, "Phiên lập kế hoạch đã hết hạn hoặc không hợp lệ. Hãy tải file lên lại.", "error")
        return redirect(request, "ai_plan_page", project_id=project_id)
    if state.get("status") == "running":
        if time.time() - state.get("started", 0) > STALE_AFTER:
            state = {**state, "status": "error",
                     "message": "Phiên lập kế hoạch bị gián đoạn (máy chủ có thể đã khởi động lại). Hãy thử lại."}
        else:
            elapsed = int(time.time() - state.get("started", time.time()))
            return render(request, "ai_plan.html", title="AI đang lập kế hoạch", state="running",
                          files=state.get("files", []), elapsed=elapsed)
    if state.get("status") != "done":
        return render(request, "ai_plan.html", title="Chưa lập được kế hoạch", state="error",
                      message=state.get("message", ""), files=state.get("files", []))

    if not state.get("audited"):
        audit.record(db, "ai_plan_done", "project", None, project_id, new={"files": state.get("files"),
                                                                            "usage": state.get("usage")})
        _write_status(token, audited=True)
    file_name = _ai_file_name(state)
    try:
        plan = imports._make_plan(db, token, {}, file_name)
    except (excel_import.ImportFormatError, excel_mapping.WorkbookReadError) as exc:
        flash(request, str(exc), "error")
        return redirect(request, "ai_plan_page", project_id=project_id)
    ctx = imports._form_context({"mode": "new", "backup": state.get("backup"), "file_name": file_name,
                                 "project_name": state.get("project_name", ""), "remember": "1"}, token)
    return imports._preview_page(request, db, project_id, plan, ctx | {
        "ai_warnings": state.get("warnings") or [], "ai_files": state.get("files", []), "ai_token": token})


def _ai_file_name(state: dict[str, Any]) -> str:
    base = (state.get("project_name") or state.get("ai_name") or "du_an").strip()
    return f"Ke_hoach_AI_{base}.xlsx"


@router.get("/import/ai/{token}/workbook", name="ai_plan_workbook")
def ai_plan_workbook(request: Request, project_id: int, token: str):
    state = _read_status(token)
    path = imports._pending_path(token)
    if state is None or path is None or not path.exists():
        raise HTTPException(status_code=404)
    name = excel_mapping.norm(_ai_file_name(state)[:-5]) or "ke_hoach_ai"
    return Response(path.read_bytes(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
