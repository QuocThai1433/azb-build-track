"""Files attached to diary entries, HSSE records and risks: validation, storage on disk and clean-up."""
from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import DB_PATH
from ..models import Attachment

ATTACH_DIR = DB_PATH.parent / "attachments"

ENTITIES = {"diary": "diary", "safety_logs": "hsse", "risks": "risks_list"}     # entity_type -> page route name
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10
MAX_FILES_PER_RECORD = 30

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".webp": "image/webp"}
DOC_TYPES = {".pdf": "application/pdf", ".doc": "application/msword",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".xls": "application/vnd.ms-excel",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             ".txt": "text/plain", ".csv": "text/csv"}
ALLOWED = {**IMAGE_TYPES, **DOC_TYPES}
ACCEPT = ",".join(sorted(ALLOWED))

_SIGNATURES = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
               ".gif": (b"GIF87a", b"GIF89a"), ".pdf": (b"%PDF",),
               ".docx": (b"PK\x03\x04",), ".xlsx": (b"PK\x03\x04",)}


class AttachmentError(ValueError):
    """The upload is refused; the message is shown to the user."""


def is_image(att: Attachment) -> bool:
    return Path(att.filename).suffix.lower() in IMAGE_TYPES


def clean_filename(name: str | None) -> str:
    base = Path((name or "").replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f<>:\"|?*]", "", base).strip(" .")
    return base[:150] or "tep-dinh-kem"


def validate(filename: str, data: bytes) -> str:
    """Return the lower-case extension, or raise AttachmentError."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise AttachmentError(f"“{filename}”: định dạng không được hỗ trợ. Cho phép: ảnh, PDF, Word, Excel, TXT, CSV.")
    if not data:
        raise AttachmentError(f"“{filename}”: tệp rỗng.")
    if len(data) > MAX_FILE_BYTES:
        raise AttachmentError(f"“{filename}”: vượt quá {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if ext == ".webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    elif ext in _SIGNATURES:
        ok = any(data.startswith(sig) for sig in _SIGNATURES[ext])
    else:
        ok = True
    if not ok:
        raise AttachmentError(f"“{filename}”: nội dung không khớp với định dạng {ext}.")
    return ext


def path_of(att: Attachment) -> Path:
    return ATTACH_DIR / str(att.project_id) / att.stored_name


def count_for(db: Session, project_id: int, entity_type: str, entity_id: int) -> int:
    return len(list(db.scalars(select(Attachment.id).where(
        Attachment.project_id == project_id, Attachment.entity_type == entity_type,
        Attachment.entity_id == entity_id))))


def save(db: Session, project_id: int, entity_type: str, entity_id: int, filename: str, data: bytes,
         uploaded_by: str | None) -> Attachment:
    ext = validate(filename, data)
    folder = ATTACH_DIR / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    (folder / stored).write_bytes(data)
    att = Attachment(project_id=project_id, entity_type=entity_type, entity_id=entity_id,
                     filename=clean_filename(filename), stored_name=stored, content_type=ALLOWED[ext],
                     size_bytes=len(data), uploaded_by=uploaded_by,
                     uploaded_at=datetime.now().isoformat(timespec="seconds"))
    db.add(att)
    db.flush()
    audit.add(db, "create", "attachments", att.id, project_id,
              new={"entity_type": entity_type, "entity_id": entity_id, "filename": att.filename,
                   "size_bytes": att.size_bytes})
    return att


def for_entities(db: Session, project_id: int, entity_type: str) -> dict[int, list[Attachment]]:
    out: dict[int, list[Attachment]] = {}
    rows = db.scalars(select(Attachment).where(Attachment.project_id == project_id,
                                               Attachment.entity_type == entity_type).order_by(Attachment.id))
    for a in rows:
        out.setdefault(a.entity_id, []).append(a)
    return out


def remove(db: Session, att: Attachment) -> None:
    audit.add(db, "delete", "attachments", att.id, att.project_id,
              old={"entity_type": att.entity_type, "entity_id": att.entity_id, "filename": att.filename})
    path = path_of(att)
    db.execute(delete(Attachment).where(Attachment.id == att.id))
    db.commit()
    path.unlink(missing_ok=True)


def remove_for_entity(db: Session, project_id: int, entity_type: str, entity_id: int) -> None:
    """Called when the diary entry / HSSE record / risk itself is deleted."""
    for att in list(db.scalars(select(Attachment).where(
            Attachment.project_id == project_id, Attachment.entity_type == entity_type,
            Attachment.entity_id == entity_id))):
        path_of(att).unlink(missing_ok=True)
        db.delete(att)
    db.commit()


def remove_project_files(project_id: int) -> None:
    shutil.rmtree(ATTACH_DIR / str(project_id), ignore_errors=True)
