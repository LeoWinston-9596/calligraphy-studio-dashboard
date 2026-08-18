from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import (
    clear_session, current_user, hash_password, set_session, verify_password,
)
from ..utils import loads_list

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _identities(u: User) -> list[str]:
    from ..teachers import user_identities
    return user_identities(u)


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.name or u.username,
        "role_label": u.role_label,
        "class_bindings": loads_list(u.class_bindings),
        "auto_bind_classes": bool(u.auto_bind_classes),
        "teacher_names": _identities(u),
        "active": bool(u.active),
        "must_change_password": bool(u.must_change_password),
    }


@router.post("/login")
def login(response: Response, username: str = Body(...), password: str = Body(...),
          db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.active:
        raise HTTPException(status_code=403, detail="账号已停用")
    set_session(response, user.id)
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..roles import permissions
    from ..teachers import resolve_classes
    return {
        **user_out(user),
        "effective_classes": resolve_classes(db, user),
        "permissions": permissions(user),
    }


@router.post("/change-password")
def change_password(old_password: str = Body(""), new_password: str = Body(...),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    # 首次登录强制改密时不校验旧密码（用户刚用初始密码登进来）
    if not user.must_change_password and not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    return user_out(user)
