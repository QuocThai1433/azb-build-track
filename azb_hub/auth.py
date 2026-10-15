"""Passwords, roles and what each role may do.

Passwords are hashed with hashlib.scrypt (standard library, no extra package). A stored hash looks like
``scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>`` so the cost can be raised later without breaking old hashes.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

ADMIN = "admin"
GIAM_DOC = "giam_doc"
NHAN_VIEN = "nhan_vien"
ROLES = (ADMIN, GIAM_DOC, NHAN_VIEN)
ROLE_LABELS = {ADMIN: "Quản trị viên", GIAM_DOC: "Giám đốc", NHAN_VIEN: "Nhân viên"}

# action -> roles allowed. Staff (nhan_vien) only enter data in the projects they are assigned to.
PERMISSIONS: dict[str, frozenset[str]] = {
    "project.create": frozenset({ADMIN, GIAM_DOC}),
    "project.archive": frozenset({ADMIN, GIAM_DOC}),
    "project.delete": frozenset({ADMIN, GIAM_DOC}),
    "project.edit": frozenset({ADMIN, GIAM_DOC}),
    "project.view_all": frozenset({ADMIN, GIAM_DOC}),
    "record.write": frozenset({ADMIN, GIAM_DOC, NHAN_VIEN}),      # create / edit
    "record.delete": frozenset({ADMIN, GIAM_DOC}),
    "cost.approve": frozenset({ADMIN, GIAM_DOC}),
    "import.run": frozenset({ADMIN, GIAM_DOC}),
    "export.run": frozenset({ADMIN, GIAM_DOC}),
    "audit.view": frozenset({ADMIN, GIAM_DOC}),
    "audit.revert": frozenset({ADMIN}),                            # undo a logged change
    "users.manage": frozenset({ADMIN}),
}

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r),
                                   p=int(p), dklen=len(digest) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def can(user, action: str) -> bool:
    """True when the signed-in user's role allows ``action`` (a key of PERMISSIONS). No user: never."""
    return user is not None and getattr(user, "role", None) in PERMISSIONS.get(action, frozenset())
