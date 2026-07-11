"""포스터 삭제 권한 — 게시자(삭제 비밀번호) 또는 관리자 세션"""

import os
import secrets

from flask import session
from werkzeug.security import check_password_hash

SESSION_ADMIN_KEY = "is_admin"


def verify_admin_password(password: str) -> bool:
    admin = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin or not password:
        return False
    return secrets.compare_digest(password, admin)


def login_admin(password: str) -> bool:
    if not verify_admin_password(password):
        return False
    session[SESSION_ADMIN_KEY] = True
    session.permanent = True
    return True


def logout_admin() -> None:
    session.pop(SESSION_ADMIN_KEY, None)


def is_admin_logged_in() -> bool:
    return bool(session.get(SESSION_ADMIN_KEY))


def can_delete_poster(poster, password: str = "") -> bool:
    """관리자 로그인 시 비밀번호 없이 삭제. 일반 사용자는 게시자 삭제 비밀번호만."""
    if is_admin_logged_in():
        return True

    if not password:
        return False

    try:
        pin_hash = poster["delete_pin_hash"]
    except (KeyError, TypeError, IndexError):
        pin_hash = None

    if not pin_hash:
        return False

    try:
        return check_password_hash(pin_hash, password)
    except (TypeError, ValueError):
        return False
