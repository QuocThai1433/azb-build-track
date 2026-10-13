"""Routes outside any single project: the home redirect and the list of projects."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import repositories as repo
from ..db import get_db
from ..services import backup as backup_service
from ..web import flash, or_404, redirect, render

router = APIRouter()

DATA_LABELS = (("tasks", "công việc"), ("costs", "khoản chi"), ("risks", "rủi ro"), ("resources", "nguồn lực"),
               ("methods", "biện pháp"), ("hsse_metrics", "chỉ tiêu HSSE"), ("safety_logs", "ghi nhận HSSE"),
               ("diary", "nhật ký"))


@router.get("/", name="home")
def home(request: Request, db: Session = Depends(get_db)):
    """Open the project the user used last; else the first active project; else the project list."""
    last = request.session.get("last_project")
    project = repo.get_project(db, last) if isinstance(last, int) else None
    if project is None or project.status != repo.ACTIVE:
        pid = repo.first_active_project_id(db)
        if pid is None:
            return redirect(request, "projects_list")
        return redirect(request, "dashboard", project_id=pid)
    return redirect(request, "dashboard", project_id=project.id)


@router.get("/projects", name="projects_list")
def projects_list(request: Request, db: Session = Depends(get_db)):
    counts = repo.data_counts_by_project(db)
    summaries = {pid: ", ".join(f"{c[key]} {label}" for key, label in DATA_LABELS if c.get(key))
                 for pid, c in counts.items()}
    return render(request, "projects.html", title="Danh sách dự án",
                  all_projects=repo.list_projects(db, include_archived=True),
                  data_counts=counts, summaries=summaries)


def _new_project_page(request: Request, db: Session, name: str = ""):
    """The two ways to add a project. The Excel upload reuses /p/<any project>/import, which always
    creates a NEW project when mode is "new", so any existing project can host the form."""
    projects = repo.list_projects(db, include_archived=True)
    host = repo.first_active_project_id(db) or (projects[0].id if projects else None)
    return render(request, "project_new.html", title="Thêm dự án mới", upload_host=host, typed_name=name)


@router.get("/projects/new", name="project_new")
def project_new(request: Request, db: Session = Depends(get_db)):
    return _new_project_page(request, db)


@router.post("/projects/new", name="project_new")
def project_create_empty(request: Request, name: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    """An empty project with just a name. Everything else can be filled in later or imported from Excel."""
    name = name.strip()
    if not name:
        flash(request, "Hãy nhập tên dự án.", "error")
        return _new_project_page(request, db)
    project = repo.new_project({"name": name[:200], "client": "", "contractor": "", "package_name": "",
                                "description": "", "report_date": date.today().isoformat(), "contract_value": 0,
                                "prelim_budget": 0, "planned_progress": 0, "source_file": None,
                                "notes": "Tạo thủ công. Có thể nhập dữ liệu từ Excel ở mục Nhập dữ liệu Excel."})
    db.add(project)
    db.commit()
    flash(request, f"Đã tạo dự án “{project.name}”. Dự án đang trống, bạn có thể nhập dữ liệu từ Excel hoặc thêm tay.",
          "success")
    return redirect(request, "dashboard", project_id=project.id)


@router.post("/{project_id:project}/archive", name="project_archive")
def project_archive(request: Request, project_id: int, db: Session = Depends(get_db)):
    project = or_404(repo.get_project(db, project_id))
    repo.set_project_status(db, project_id, repo.ARCHIVED)
    if request.session.get("last_project") == project_id:
        request.session.pop("last_project", None)
    flash(request, f"Đã lưu trữ dự án “{project.name}”. Dữ liệu vẫn còn, bạn có thể khôi phục bất cứ lúc nào.", "success")
    return redirect(request, "projects_list")


@router.post("/{project_id:project}/restore", name="project_restore")
def project_restore(request: Request, project_id: int, db: Session = Depends(get_db)):
    project = or_404(repo.get_project(db, project_id))
    repo.set_project_status(db, project_id, repo.ACTIVE)
    flash(request, f"Đã khôi phục dự án “{project.name}”.", "success")
    return redirect(request, "projects_list")


@router.post("/{project_id:project}/delete", name="project_delete")
def project_delete(request: Request, project_id: int, db: Session = Depends(get_db)):
    """Delete a project for good. The user confirms in a dialog before this is sent.
    Checked in this order: never the last project, then a database backup is made first.
    If the backup fails, nothing is deleted."""
    project = or_404(repo.get_project(db, project_id))
    name = project.name
    if len(repo.list_projects(db, include_archived=True)) <= 1:
        flash(request, "Không thể xoá dự án cuối cùng. Ứng dụng cần ít nhất một dự án.", "error")
        return redirect(request, "projects_list")
    try:
        backup_file = backup_service.create_backup(label="truoc_xoa_du_an")
    except Exception as exc:
        flash(request, f"Không tạo được bản sao lưu nên chưa xoá gì. Chi tiết: {exc}", "error")
        return redirect(request, "projects_list")

    repo.delete_project(db, project_id)
    if request.session.get("last_project") == project_id:
        request.session.pop("last_project", None)
    flash(request, f"Đã xoá vĩnh viễn dự án “{name}” và toàn bộ dữ liệu của nó. "
                   f"Bản sao lưu trước khi xoá: {backup_file.parent.name}/{backup_file.name}.", "success")
    return redirect(request, "projects_list")
