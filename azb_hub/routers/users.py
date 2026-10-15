"""Account management (admin only): create users, set the role, lock an account, assign projects."""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import audit, auth
from .. import repositories as repo
from ..auth import ROLE_LABELS, ROLES
from ..db import get_db
from ..models import User
from ..web import flash, or_404, redirect, render
from .deps import require

router = APIRouter(dependencies=[Depends(require("users.manage"))])
MIN_PASSWORD = 8


def _form_page(request: Request, db: Session, item: User | None):
    projects = repo.list_projects(db, include_archived=True)
    assigned = repo.member_project_ids(db, item.id) if item else set()
    return render(request, "user_form.html", title="Sửa tài khoản" if item else "Thêm tài khoản", item=item,
                  roles=[(r, ROLE_LABELS[r]) for r in ROLES], all_projects=projects, assigned=assigned)


def _project_ids(form) -> set[int]:
    return {int(v) for v in form.getlist("projects") if str(v).isdigit()}


@router.get("/users", name="users_list")
def users_list(request: Request, db: Session = Depends(get_db)):
    users = repo.list_users(db)
    counts = {u.id: len(repo.member_project_ids(db, u.id)) for u in users}
    return render(request, "users.html", title="Tài khoản", users=users, counts=counts, role_labels=ROLE_LABELS)


@router.get("/users/new", name="user_new")
def user_new(request: Request, db: Session = Depends(get_db)):
    return _form_page(request, db, None)


@router.post("/users/new", name="user_new")
async def user_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    role = str(form.get("role", "nhan_vien"))
    if not username or role not in ROLES:
        flash(request, "Nhập tên đăng nhập và chọn vai trò.", "error")
    elif repo.get_user_by_username(db, username) is not None:
        flash(request, "Tên đăng nhập này đã có người dùng.", "error")
    elif len(password) < MIN_PASSWORD:
        flash(request, f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.", "error")
    else:
        user = User(username=username, full_name=str(form.get("full_name", "")).strip(), role=role,
                    password_hash=auth.hash_password(password), must_change_password=True,
                    created_at=datetime.now().isoformat(timespec="seconds"))
        db.add(user)
        db.flush()
        repo.set_memberships(db, user.id, _project_ids(form))
        audit.add(db, "create", "users", user.id, new={"username": username, "role": role})
        db.commit()
        flash(request, f"Đã tạo tài khoản “{username}”. Người dùng sẽ phải đổi mật khẩu khi đăng nhập lần đầu.",
              "success")
        return redirect(request, "users_list")
    return _form_page(request, db, None)


@router.get("/users/{user_id}/edit", name="user_edit")
def user_edit(request: Request, user_id: int, db: Session = Depends(get_db)):
    return _form_page(request, db, or_404(repo.get_user(db, user_id)))


@router.post("/users/{user_id}/edit", name="user_edit")
async def user_save(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = or_404(repo.get_user(db, user_id))
    form = await request.form()
    role = str(form.get("role", user.role))
    active = form.get("is_active") == "1"
    password = str(form.get("password", ""))
    me: User = request.state.user
    if role not in ROLES:
        flash(request, "Vai trò không hợp lệ.", "error")
    elif user.id == me.id and (role != auth.ADMIN or not active):
        flash(request, "Bạn không thể tự hạ quyền hoặc khóa chính tài khoản của mình.", "error")
    elif password and len(password) < MIN_PASSWORD:
        flash(request, f"Mật khẩu mới cần ít nhất {MIN_PASSWORD} ký tự.", "error")
    else:
        before = {"full_name": user.full_name, "role": user.role, "is_active": user.is_active,
                  "projects": sorted(repo.member_project_ids(db, user.id))}
        user.full_name = str(form.get("full_name", "")).strip()
        user.role, user.is_active = role, active
        if password:
            user.password_hash = auth.hash_password(password)
            user.must_change_password = True
        projects = _project_ids(form)
        repo.set_memberships(db, user.id, projects)
        after = {"full_name": user.full_name, "role": user.role, "is_active": user.is_active,
                 "projects": sorted(projects)}
        if password:
            after["password"] = "reset"
        old, new = audit.diff(before, after)
        audit.add(db, "update", "users", user.id, old=old, new=new)
        db.commit()
        flash(request, "Đã lưu tài khoản.", "success")
        return redirect(request, "users_list")
    return _form_page(request, db, user)
