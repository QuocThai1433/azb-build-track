"""Upload, download and delete of photos / documents on diary entries, HSSE records and risks."""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import auth
from .. import repositories as repo
from ..db import get_db
from ..models import Attachment, Diary, Risk, SafetyLog
from ..services import attachments as svc
from ..web import flash, or_404, redirect
from .deps import require

router = APIRouter()

ENTITY_MODELS = {"diary": Diary, "safety_logs": SafetyLog, "risks": Risk}


@router.post("/attachments", name="attachment_upload", dependencies=[Depends(require("record.write"))])
async def attachment_upload(request: Request, project_id: int, entity_type: Annotated[str, Form()],
                            entity_id: Annotated[int, Form()], files: Annotated[list[UploadFile], File()] = (),
                            db: Session = Depends(get_db)):
    if entity_type not in ENTITY_MODELS:
        flash(request, "Loại bản ghi không hợp lệ.", "error")
        return redirect(request, "dashboard")
    back = svc.ENTITIES[entity_type]
    record = repo.get(db, ENTITY_MODELS[entity_type], project_id, entity_id)
    if record is None:
        flash(request, "Không tìm thấy bản ghi để đính kèm.", "error")
        return redirect(request, back)
    files = [f for f in files if f.filename]
    if not files:
        flash(request, "Hãy chọn ít nhất một tệp.", "error")
        return redirect(request, back)
    if len(files) > svc.MAX_FILES_PER_UPLOAD:
        flash(request, f"Mỗi lần chỉ tải tối đa {svc.MAX_FILES_PER_UPLOAD} tệp.", "error")
        return redirect(request, back)
    existing = svc.count_for(db, project_id, entity_type, entity_id)
    if existing + len(files) > svc.MAX_FILES_PER_RECORD:
        flash(request, f"Mỗi bản ghi chỉ đính kèm tối đa {svc.MAX_FILES_PER_RECORD} tệp.", "error")
        return redirect(request, back)

    user = request.state.user
    saved, errors = 0, []
    for f in files:
        data = await f.read(svc.MAX_FILE_BYTES + 1)
        try:
            svc.save(db, project_id, entity_type, entity_id, f.filename, data, user.username if user else None)
            saved += 1
        except svc.AttachmentError as exc:
            errors.append(str(exc))
    db.commit()
    if saved:
        flash(request, f"Đã đính kèm {saved} tệp.", "success")
    for message in errors[:3]:
        flash(request, message, "error")
    return redirect(request, back)


@router.get("/attachments/{attachment_id}", name="attachment_download")
def attachment_download(request: Request, project_id: int, attachment_id: int, db: Session = Depends(get_db)):
    att = or_404(repo.get(db, Attachment, project_id, attachment_id))
    path = svc.path_of(att)
    if not path.is_file():
        or_404(None)
    inline = svc.is_image(att) or att.filename.lower().endswith(".pdf")
    disposition = "inline" if inline else "attachment"
    headers = {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(att.filename)}",
               "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}
    return FileResponse(path, media_type=att.content_type or "application/octet-stream", headers=headers)


@router.post("/attachments/{attachment_id}/delete", name="attachment_delete",
             dependencies=[Depends(require("record.write"))])
def attachment_delete(request: Request, project_id: int, attachment_id: int, db: Session = Depends(get_db)):
    att = or_404(repo.get(db, Attachment, project_id, attachment_id))
    user = request.state.user
    if not auth.can(user, "record.delete") and att.uploaded_by != getattr(user, "username", None):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Bạn chỉ xóa được tệp do chính mình tải lên.")
    back = svc.ENTITIES.get(att.entity_type, "dashboard")
    svc.remove(db, att)
    flash(request, "Đã xóa tệp đính kèm.", "success")
    return redirect(request, back)
