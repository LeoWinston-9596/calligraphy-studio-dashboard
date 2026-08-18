"""用户管理页。

账号操作按角色分级（见 app/roles.py）；业务数据不受影响，仍是所有人可看可改。
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..roles import (
    ROLE_LABELS, assert_create, assert_edit, assert_toggle, can_edit,
    can_toggle_active, permissions,
)
from ..security import current_user, hash_password
from ..teachers import (
    match_teacher_names, resolve_classes, teacher_class_map, teacher_summary,
)
from ..utils import dumps
from .auth import user_out

router = APIRouter(prefix="/api/users", tags=["users"])


def user_row(db: Session, u: User, me: User) -> dict:
    return {
        **user_out(u),
        "effective_classes": resolve_classes(db, u),
        "can_edit": can_edit(me, u),
        "can_toggle_active": can_toggle_active(me, u),
    }


@router.get("")
def list_users(db: Session = Depends(get_db), me: User = Depends(current_user)):
    rows = db.query(User).order_by(User.active.desc(), User.id).all()
    return {
        "items": [user_row(db, u, me) for u in rows],
        "permissions": permissions(me),
        "role_labels": ROLE_LABELS,
    }


@router.get("/teachers")
def teachers(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """导入表里出现过的老师及其班级，供创建账号时一键匹配。"""
    return teacher_summary(db)


@router.get("/match-teacher")
def match_teacher(name: str = Query(...), db: Session = Depends(get_db),
                  _: User = Depends(current_user)):
    """按姓名猜测对应的导入表老师身份（可能多个），注册时用来自动勾选。"""
    matched = match_teacher_names(db, name)
    cmap = teacher_class_map(db)
    classes: list[str] = []
    for who in matched:
        for cls in cmap.get(who, []):
            if cls not in classes:
                classes.append(cls)
    return {"input": name, "matched": matched, "classes": sorted(classes)}


@router.post("")
def create_user(username: str = Body(...), password: str = Body(...), name: str = Body(""),
                role_label: str = Body("老师"), class_bindings: list[str] = Body([]),
                auto_bind_classes: bool = Body(True),
                teacher_names: list[str] = Body(None),
                db: Session = Depends(get_db), me: User = Depends(current_user)):
    assert_create(me, role_label)

    username = username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    display_name = name.strip() or username
    # 没勾身份就按姓名自动对到导入表里的老师（可能匹配到多个）
    identities = [str(x).strip() for x in (teacher_names or []) if str(x).strip()]
    if not identities:
        identities = match_teacher_names(db, display_name)

    u = User(
        username=username,
        password_hash=hash_password(password),
        name=display_name,
        role_label=role_label,
        class_bindings=dumps(class_bindings or []),
        auto_bind_classes=bool(auto_bind_classes),
        teacher_names=dumps(identities),
        active=True,
        must_change_password=False,
    )
    db.add(u)
    db.commit()
    return user_row(db, u, me)


@router.patch("/{user_id}")
def update_user(user_id: int, payload: dict = Body(...),
                db: Session = Depends(get_db), me: User = Depends(current_user)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")

    new_role = payload.get("role_label") if payload.get("role_label") in ROLE_LABELS else None
    assert_edit(me, u, new_role)

    if "name" in payload:
        u.name = str(payload["name"]).strip() or u.username
    if new_role:
        u.role_label = new_role
    if "class_bindings" in payload:
        u.class_bindings = dumps(payload["class_bindings"] or [])
    if "auto_bind_classes" in payload:
        u.auto_bind_classes = bool(payload["auto_bind_classes"])
    if "teacher_names" in payload:
        u.teacher_names = dumps([str(x).strip() for x in (payload["teacher_names"] or [])
                                 if str(x).strip()])

    if "active" in payload:
        active = bool(payload["active"])
        if active != bool(u.active):
            assert_toggle(me, u)
            if not active and db.query(User).filter(User.active == True).count() <= 1:  # noqa: E712
                raise HTTPException(status_code=400, detail="至少要保留一个可用账号")
            u.active = active

    if payload.get("password"):
        if len(payload["password"]) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        u.password_hash = hash_password(payload["password"])
        u.must_change_password = False

    db.commit()
    return user_row(db, u, me)
