"""账号、密码、会话（规格书 §2）。

所有登录用户可查看/编辑一切数据；role_label 与 class_bindings 仅作显示和默认筛选，
不做任何权限拦截。
"""
from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import DATA_DIR, SESSION_COOKIE, SESSION_MAX_AGE
from .db import get_db
from .models import User

_SECRET_FILE = DATA_DIR / "secret.key"


def _secret() -> str:
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(48)
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_text(key, encoding="utf-8")
    return key


_serializer = URLSafeTimedSerializer(_secret(), salt="sbs-session")


def hash_password(raw: str) -> str:
    # bcrypt 只处理前 72 字节
    return bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def set_session(response: Response, user_id: int, secure_hint: bool = False) -> None:
    token = _serializer.dumps({"uid": user_id})
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", path="/",
        # 局域网内 http 与 https 双端口都要能用，因此不强制 secure
        secure=False,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        # 便于手机端 <img>/<audio> 之外的调用，也支持 Authorization 头
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.get(User, data.get("uid"))
    if user and user.active:
        return user
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return _user_from_request(request, db)


def ensure_admin_seed(db: Session) -> None:
    """内置初始账号 admin/admin123，首次登录强制改密。"""
    if db.query(User).count() == 0:
        db.add(User(
            username="admin",
            password_hash=hash_password("admin123"),
            name="管理员",
            role_label="校长",
            class_bindings="[]",
            active=True,
            must_change_password=True,
        ))
        db.commit()
