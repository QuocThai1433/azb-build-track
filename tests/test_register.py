"""Staff sign-up: the account is created switched off, and only an admin switches it on."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from azb_hub.db import SessionLocal
from azb_hub.main import app
from azb_hub.models import AuditLog, User

GOOD = {"full_name": "Lê Văn Mới", "password": "Mat-khau-moi-1", "confirm": "Mat-khau-moi-1"}


def _guest() -> TestClient:
    return TestClient(app, follow_redirects=False)


def _user(username: str) -> User | None:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.username == username))


def test_sign_up_form_is_open_to_guests(client):
    r = _guest().get("/register")
    assert r.status_code == 200 and 'name="username"' in r.text


def test_sign_up_creates_a_switched_off_staff_account(client):
    r = _guest().post("/register", data={**GOOD, "username": "le.van.moi"})
    assert r.status_code == 303 and r.headers["location"] == "/login"
    user = _user("le.van.moi")
    assert user.is_active is False and user.role == "nhan_vien" and user.must_change_password is False
    assert user.password_hash != GOOD["password"]                       # stored hashed
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "create", AuditLog.entity_type == "users",
                                                AuditLog.entity_id == user.id)).new_value.count("dang_ky") == 1


def test_switched_off_account_cannot_sign_in_until_admin_enables_it(client):
    guest = _guest()
    assert guest.post("/register", data={**GOOD, "username": "cho-duyet"}).status_code == 303
    assert _guest().post("/login", data={"username": "cho-duyet", "password": GOOD["password"]}).status_code == 200
    with SessionLocal() as db:
        db.get(User, _user("cho-duyet").id).is_active = True
        db.commit()
    assert _guest().post("/login", data={"username": "cho-duyet", "password": GOOD["password"]}).status_code == 303


def test_sign_up_refuses_bad_input(client):
    cases = [
        {"username": "ab"},                                             # too short
        {"username": "có dấu"},                                         # not allowed characters
        {"username": "admin"},                                          # already taken
        {"username": "mat-khau-ngan", "password": "123", "confirm": "123"},
        {"username": "lech-nhau", "confirm": "khac-di-hoan-toan"},
    ]
    for case in cases:
        data = {**GOOD, "username": "mat-khau-ngan", **case}
        r = _guest().post("/register", data=data)
        assert r.status_code == 200, case
    assert _user("mat-khau-ngan") is None and _user("lech-nhau") is None


def test_signed_in_user_is_sent_home_from_the_form(client):
    assert client.get("/register").headers["location"] == "/"
