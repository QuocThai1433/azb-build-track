"""Excel import of one project in three steps: upload -> preview (check and fix the column mapping) -> confirm.

Nothing is written to the data tables before the user confirms. The uploaded file waits in
instance/uploads/pending_<token>.xlsx between the steps.
"""
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import audit
from .. import repositories as repo
from ..constants import MAX_UPLOAD_BYTES
from ..db import DB_PATH, get_db
from ..models import Cost, Resource, Risk, Task
from ..services import backup as backup_service
from ..services import excel_import, excel_mapping
from ..services.excel_mapping import ENTITIES, ENTITY_ORDER, ImportPlan, norm
from ..web import flash, redirect, render
from .deps import require

router = APIRouter(dependencies=[Depends(require("import.run"))])

UPLOAD_DIR = DB_PATH.parent / "uploads"
TOKEN = re.compile(r"^[0-9a-f]{32}$")
PENDING_MAX_AGE = 24 * 3600
STAT_LABELS = (("tasks", "công việc"), ("risks", "rủi ro"), ("costs", "khoản chi"), ("resources", "nguồn lực"),
               ("methods", "biện pháp"), ("hsse", "chỉ tiêu HSSE"))


# ---- helpers ---------------------------------------------------------------------------------

def _pending_path(token: str) -> Path | None:
    return UPLOAD_DIR / f"pending_{token}.xlsx" if TOKEN.match(token or "") else None


def _cleanup_pending() -> None:
    if not UPLOAD_DIR.exists():
        return
    limit = time.time() - PENDING_MAX_AGE
    for f in [*UPLOAD_DIR.glob("pending_*.xlsx"), *UPLOAD_DIR.glob("ai_*")]:     # ai_*: see ai_plan.py
        try:
            if f.stat().st_mtime < limit:
                f.unlink()
        except OSError:
            pass


def _upload_page(request: Request, db: Session, project_id: int):
    counts = {"tasks": repo.count_rows(db, Task, project_id), "costs": repo.count_rows(db, Cost, project_id),
              "risks": repo.count_rows(db, Risk, project_id), "resources": repo.count_rows(db, Resource, project_id)}
    return render(request, "import.html", title="Cập nhật từ Excel", counts=counts,
                  backups=backup_service.list_backups(), aliases=repo.list_aliases(db))


def _overrides_from_form(form: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Turn the preview form into what build_plan understands. Only real user choices become overrides:
    a column counts when its select differs from what the page showed (was_), or it was already manual (man_)."""
    overrides: dict[str, dict[str, Any]] = {}
    for key in ENTITY_ORDER:
        sheet_key = f"sheet_{key}"
        if sheet_key not in form:
            continue
        chosen = str(form[sheet_key])
        prev = str(form.get(f"prev_sheet_{key}", ""))
        manual_sheet = form.get(f"msheet_{key}") == "1"
        entry: dict[str, Any] = {}
        if chosen != prev or manual_sheet:
            entry["sheet"] = chosen
        if chosen == prev:
            columns: dict[int, str] = {}
            prefix = f"col_{key}_"
            for name, value in form.items():
                if not name.startswith(prefix):
                    continue
                idx = name[len(prefix):]
                if not idx.isdigit():
                    continue
                was = str(form.get(f"was_{key}_{idx}", ""))
                if str(value) != was or form.get(f"man_{key}_{idx}") == "1":
                    columns[int(idx)] = str(value)
            if columns:
                entry["columns"] = columns
        if entry:
            overrides[key] = entry
    return overrides


def _make_plan(db: Session, token: str, overrides: dict, file_name: str) -> ImportPlan:
    path = _pending_path(token)
    if path is None or not path.exists():
        raise excel_import.ImportFormatError("Phiên nhập đã hết hạn hoặc không hợp lệ. Hãy chọn lại file.")
    sheets = excel_mapping.load_sheets(path)
    return excel_mapping.build_plan(sheets, file_name, repo.load_aliases(db), overrides)


def _preview_page(request: Request, db: Session, project_id: int, plan: ImportPlan, ctx: dict[str, Any]):
    project = repo.get_project(db, project_id)
    matches = excel_import.preview_matches(db, project_id, plan) if ctx["mode"] == "update" else {}
    return render(request, "import_preview.html", title="Xem trước khi nhập", plan=plan, project_name_now=project.name,
                  entity_order=ENTITY_ORDER, entity_specs=ENTITIES, matches=matches, stat_labels=STAT_LABELS,
                  choices={k: [(f.key, f.label) for f in ENTITIES[k].fields] for k in ENTITY_ORDER}, **ctx)


def _form_context(form: dict[str, Any], token: str) -> dict[str, Any]:
    return {"token": token, "mode": "update" if form.get("mode") == "update" else "new",
            "backup": "no" if form.get("backup") == "no" else "yes",
            "new_name": str(form.get("project_name", "")).strip(),
            "remember": form.get("remember") == "1",       # an unticked box sends nothing
            "file_name": str(form.get("file_name", ""))}


# ---- step 1: the page and the upload ---------------------------------------------------------

@router.get("/import", name="import_page")
def import_page(request: Request, project_id: int, db: Session = Depends(get_db)):
    return _upload_page(request, db, project_id)


@router.post("/import", name="import_page")
def import_upload(request: Request, project_id: int, workbook: UploadFile | None = File(None),
                  mode: Annotated[str, Form()] = "new", backup: Annotated[str, Form()] = "yes",
                  project_name: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    """Check the file is a readable .xlsx, keep it as a pending file, and show the preview."""
    if workbook is None or not workbook.filename:
        flash(request, "Chọn file Excel (.xlsx) trước khi nhập.", "error")
        return _upload_page(request, db, project_id)
    if not workbook.filename.lower().endswith(".xlsx"):
        flash(request, "Chỉ hỗ trợ file .xlsx.", "error")
        return _upload_page(request, db, project_id)
    data = workbook.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        flash(request, "File tải lên vượt quá giới hạn 20 MB.", "error")
        return _upload_page(request, db, project_id)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_pending()
    token = secrets.token_hex(16)
    path = UPLOAD_DIR / f"pending_{token}.xlsx"
    path.write_bytes(data)
    original_name = Path(workbook.filename).name
    try:
        plan = excel_mapping.build_plan(excel_mapping.load_sheets(path), original_name, repo.load_aliases(db), {})
    except excel_mapping.WorkbookReadError as exc:
        path.unlink(missing_ok=True)
        flash(request, f"File “{original_name}”: {exc} Chưa nhập gì.", "error")
        return _upload_page(request, db, project_id)

    ctx = _form_context({"mode": mode, "backup": backup, "project_name": project_name, "file_name": original_name,
                         "remember": "1"}, token)
    return _preview_page(request, db, project_id, plan, ctx)


# ---- step 2: re-check after the user changed a sheet or a column -----------------------------

@router.post("/import/preview", name="import_preview")
async def import_preview(request: Request, project_id: int, db: Session = Depends(get_db)):
    form = dict(await request.form())
    return await run_in_threadpool(_preview_step, request, db, project_id, form)


def _preview_step(request: Request, db: Session, project_id: int, form: dict[str, Any]):
    ctx = _form_context(form, str(form.get("token", "")))
    try:
        plan = _make_plan(db, ctx["token"], _overrides_from_form(form), ctx["file_name"])
    except (excel_import.ImportFormatError, excel_mapping.WorkbookReadError) as exc:
        flash(request, str(exc), "error")
        return _upload_page(request, db, project_id)
    return _preview_page(request, db, project_id, plan, ctx)


# ---- step 3: backup, then write ---------------------------------------------------------------

@router.post("/import/confirm", name="import_confirm")
async def import_confirm(request: Request, project_id: int, db: Session = Depends(get_db)):
    form = dict(await request.form())
    return await run_in_threadpool(_confirm_step, request, db, project_id, form)


def _remember_choices(db: Session, plan: ImportPlan, overrides: dict[str, dict[str, Any]]) -> None:
    """Save what the user chose by hand, so the next file with the same headers needs no fixing."""
    for key, entry in overrides.items():
        ep = plan.entities.get(key)
        if ep is None:
            continue
        if entry.get("sheet") and ep.sheet:
            repo.save_alias(db, "sheet", key, norm(ep.sheet), ep.sheet, "")
        by_index = {c.index: c for c in ep.columns}
        for idx, field in (entry.get("columns") or {}).items():
            col = by_index.get(idx)
            if col is not None and col.norm:
                repo.save_alias(db, "column", key, col.norm, col.header, field or "")
    db.commit()


def _confirm_step(request: Request, db: Session, project_id: int, form: dict[str, Any]):
    ctx = _form_context(form, str(form.get("token", "")))
    overrides = _overrides_from_form(form)
    try:
        plan = _make_plan(db, ctx["token"], overrides, ctx["file_name"])
    except (excel_import.ImportFormatError, excel_mapping.WorkbookReadError) as exc:
        flash(request, str(exc), "error")
        return _upload_page(request, db, project_id)
    # Only the project name is required. Any missing sheet, column or cell stays empty.
    if ctx["mode"] != "update":
        if not (ctx["new_name"] or str(plan.project.get("name") or "").strip()):
            flash(request, "Chưa có tên dự án: file không ghi tên dự án. Hãy nhập tên vào ô “Tên dự án” rồi bấm Nhập.",
                  "error")
            return _preview_page(request, db, project_id, plan, ctx)
    elif not plan.has_data and not plan.project:
        flash(request, "File không có dữ liệu hay thông tin dự án nào nhận ra được, nên không có gì để cập nhật. "
                       "Hãy kiểm tra sheet và cột ở bảng bên dưới.", "error")
        return _preview_page(request, db, project_id, plan, ctx)

    backup_note = " Bạn đã chọn không sao lưu trước khi nhập."
    if ctx["backup"] != "no":
        try:
            backup_file = backup_service.create_backup()
        except Exception as exc:
            flash(request, f"Không tạo được bản sao lưu nên chưa nhập gì. Dữ liệu cũ vẫn nguyên. Chi tiết: {exc}", "error")
            return _preview_page(request, db, project_id, plan, ctx)
        backup_note = f" Đã sao lưu database vào {backup_file.parent.name}/{backup_file.name} trước khi nhập."

    try:
        if ctx["mode"] == "update":
            stats = excel_import.import_into_project(db, project_id, plan)
            target = project_id
            head = "Đã cập nhật dự án này từ file"
            tail = (f" Giữ tiến độ thực tế cho {stats['matched_id']} công việc khớp mã WBS"
                    f" và {stats['matched_title']} công việc khớp tên.")
        else:
            project, stats = excel_import.import_as_new_project(db, plan, ctx["new_name"])
            target = project.id
            head = f"Đã tạo dự án mới “{project.name}” từ file"
            tail = " Các dự án khác không thay đổi."
    except Exception as exc:
        flash(request, f"Không thể nhập file. Dữ liệu cũ vẫn nguyên. Chi tiết: {exc}", "error")
        return _preview_page(request, db, project_id, plan, ctx)

    if ctx["remember"]:
        try:
            _remember_choices(db, plan, overrides)
        except Exception:
            db.rollback()

    counts = ", ".join(f"{stats[k]} {label}" for k, label in STAT_LABELS if stats.get(k))
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", ctx["file_name"]) or "ke_hoach.xlsx"
    pending = _pending_path(ctx["token"])
    if pending is not None and pending.exists():
        try:
            shutil.move(str(pending), str(UPLOAD_DIR / safe))
        except OSError:
            pass
    audit.record(db, "import", "project", target, target,
                 new={"file": ctx["file_name"], "mode": ctx["mode"], "stats": stats})
    flash(request, f"{head}: {counts or 'không có dữ liệu'}.{tail}{backup_note}", "success")
    return redirect(request, "dashboard" if ctx["mode"] != "update" else "import_page", project_id=target)


# ---- remembered choices ----------------------------------------------------------------------

@router.post("/import/aliases/{alias_id}/delete", name="import_alias_delete")
def import_alias_delete(request: Request, project_id: int, alias_id: int, db: Session = Depends(get_db)):
    repo.delete_alias(db, alias_id)
    flash(request, "Đã xoá lựa chọn đã ghi nhớ.", "success")
    return redirect(request, "import_page")
