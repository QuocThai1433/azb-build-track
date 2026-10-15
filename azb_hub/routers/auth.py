"""Sign in, sign out and change password."""
import re
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from .. import repositories as repo
from ..auth import hash_password, verify_password
from ..db import get_db
from ..models import AuditLog, User
from ..web import flash, render

router = APIRouter()

MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_PASSWORD = 8


def _safe_next(target: str) -> str:
    """Only local paths: '/abc' is fine, '//evil.test' and 'https://...' are not."""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else "/"


def _is_locked(db: Session, username: str) -> bool:
    since = (datetime.now() - timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
    last_ok = db.scalar(select(func.max(AuditLog.created_at)).where(
        AuditLog.action == "login", AuditLog.username == username)) or ""
    failed = db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "login_failed", AuditLog.username == username,
        AuditLog.created_at >= max(since, last_ok))) or 0
    return failed >= MAX_FAILED


@router.get("/login", name="login")
def login_page(request: Request, next: str = ""):
    if getattr(request.state, "user", None) is not None:
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", title="Đăng nhập", next=_safe_next(next), username="")


@router.post("/login", name="login")
def login(request: Request, username: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
          next: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    username = username.strip()
    actor = audit.current_actor()
    user = repo.get_user_by_username(db, username)

    def fail(message: str):
        audit.record(db, "login_failed", "user", user.id if user else None, new={"username": username[:80]},
                     actor=audit.Actor(user.id if user else None, username[:80] or None, actor.ip_address,
                                       actor.user_agent))
        flash(request, message, "error")
        return render(request, "login.html", title="Đăng nhập", next=_safe_next(next), username=username)

    if user is not None and _is_locked(db, user.username):
        return fail(f"Tài khoản tạm khóa {LOCK_MINUTES} phút do nhập sai nhiều lần.")
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return fail("Sai tên đăng nhập hoặc mật khẩu, hoặc tài khoản đã bị khóa.")

    request.session.clear()                                   # drop anything left from before sign-in
    request.session["user_id"] = user.id
    user.last_login_at = datetime.now().isoformat(timespec="seconds")
    audit.record(db, "login", "user", user.id, actor=audit.Actor(user.id, user.username, actor.ip_address,
                                                                 actor.user_agent))
    return RedirectResponse(_safe_next(next), status_code=303)


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


@router.get("/register", name="register")
def register_page(request: Request):
    if getattr(request.state, "user", None) is not None:
        return RedirectResponse("/", status_code=303)
    return render(request, "register.html", title="Đăng ký tài khoản", full_name="", username="")


@router.post("/register", name="register")
def register_submit(request: Request, full_name: Annotated[str, Form()] = "",
                    username: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
                    confirm: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    """A staff member asks for an account. It is created switched off; an admin switches it on and assigns projects."""
    full_name, username = full_name.strip(), username.strip()
    if not full_name or not username:
        flash(request, "Nhập họ tên và tên đăng nhập.", "error")
    elif not USERNAME_PATTERN.match(username):
        flash(request, "Tên đăng nhập 3–32 ký tự, chỉ gồm chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch ngang.", "error")
    elif repo.get_user_by_username(db, username) is not None:
        flash(request, "Tên đăng nhập này đã có người dùng. Hãy chọn tên khác.", "error")
    elif len(password) < MIN_PASSWORD:
        flash(request, f"Mật khẩu cần ít nhất {MIN_PASSWORD} ký tự.", "error")
    elif password != confirm:
        flash(request, "Hai lần nhập mật khẩu không giống nhau.", "error")
    else:
        user = User(username=username, full_name=full_name, role="nhan_vien", is_active=False,
                    password_hash=hash_password(password), must_change_password=False,
                    created_at=datetime.now().isoformat(timespec="seconds"))
        db.add(user)
        db.flush()
        audit.add(db, "create", "users", user.id, new={"username": username, "role": "nhan_vien", "source": "dang_ky"},
                  actor=audit.Actor(None, username, audit.current_actor().ip_address, audit.current_actor().user_agent))
        db.commit()
        flash(request, "Đã gửi đăng ký. Quản trị viên sẽ kích hoạt tài khoản và giao dự án cho bạn.", "success")
        return RedirectResponse("/login", status_code=303)
    return render(request, "register.html", title="Đăng ký tài khoản", full_name=full_name, username=username)


@router.post("/logout", name="logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None)
    if user is not None:
        audit.record(db, "logout", "user", user.id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/account/password", name="account_password")
def password_page(request: Request):
    return render(request, "account_password.html", title="Đổi mật khẩu")


@router.post("/account/password", name="account_password")
def password_save(request: Request, current: Annotated[str, Form()] = "", new: Annotated[str, Form()] = "",
                  confirm: Annotated[str, Form()] = "", db: Session = Depends(get_db)):
    user: User = request.state.user
    row = db.get(User, user.id)
    if not verify_password(current, row.password_hash):
        flash(request, "Mật khẩu hiện tại không đúng.", "error")
    elif len(new) < MIN_PASSWORD:
        flash(request, f"Mật khẩu mới cần ít nhất {MIN_PASSWORD} ký tự.", "error")
    elif new != confirm:
        flash(request, "Hai lần nhập mật khẩu mới không giống nhau.", "error")
    elif new == current:
        flash(request, "Mật khẩu mới phải khác mật khẩu cũ.", "error")
    else:
        row.password_hash = hash_password(new)
        row.must_change_password = False
        audit.record(db, "update", "users", row.id, new={"password": "changed"})
        flash(request, "Đã đổi mật khẩu.", "success")
        return RedirectResponse("/", status_code=303)
    return render(request, "account_password.html", title="Đổi mật khẩu")
