"""账号角色分级 —— 只管「用户管理」，不限制业务数据。

规则（客户确认）：
  校长 > 教务 > 老师
  · 新增账号：仅 校长 / 教务 可用，且只能建同级与下级
  · 停用/启用：只能操作严格下级（校长可停用教务和老师，教务可停用老师，老师不可停用任何人）
  · 编辑他人资料：只能编辑同级与下级；本人始终可改自己的姓名与密码

业务数据（学员、课时、作品、评价、导入、订单收支）仍然是所有登录用户都能看和改，
靠编辑留痕保证可追溯 —— 这部分未变。
"""
from __future__ import annotations

from fastapi import HTTPException

from .models import User

ROLE_LABELS = ["校长", "教务", "老师"]
RANK = {"校长": 1, "教务": 2, "老师": 3}


def rank(role_label: str) -> int:
    return RANK.get(role_label or "", 99)


def can_create(actor: User) -> bool:
    """老师不能新增账号。"""
    return rank(actor.role_label) <= RANK["教务"]


def creatable_roles(actor: User) -> list[str]:
    """能创建的角色：同级与下级。"""
    if not can_create(actor):
        return []
    return [r for r in ROLE_LABELS if rank(r) >= rank(actor.role_label)]


def can_toggle_active(actor: User, target: User) -> bool:
    """停用/启用只能对严格下级。"""
    if actor.id == target.id:
        return False
    return rank(actor.role_label) < rank(target.role_label)


def can_edit(actor: User, target: User) -> bool:
    """编辑资料：本人，或同级与下级。"""
    if actor.id == target.id:
        return True
    return rank(actor.role_label) <= rank(target.role_label)


def assert_create(actor: User, role_label: str) -> None:
    if not can_create(actor):
        raise HTTPException(status_code=403,
                            detail="老师账号不能新增用户，请联系教务或校长")
    if role_label not in creatable_roles(actor):
        raise HTTPException(
            status_code=403,
            detail=f"{actor.role_label}只能创建 {'、'.join(creatable_roles(actor))} 账号")


def assert_toggle(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise HTTPException(status_code=400, detail="不能停用自己的账号")
    if not can_toggle_active(actor, target):
        raise HTTPException(
            status_code=403,
            detail=f"{actor.role_label}不能停用{target.role_label}账号，只能停用下级")


def assert_edit(actor: User, target: User, new_role: str | None = None) -> None:
    if not can_edit(actor, target):
        raise HTTPException(status_code=403,
                            detail=f"{actor.role_label}不能修改{target.role_label}的账号")
    if new_role is not None and new_role != target.role_label:
        if not can_create(actor):
            raise HTTPException(status_code=403, detail="老师账号不能修改角色")
        if new_role not in creatable_roles(actor):
            raise HTTPException(status_code=403,
                                detail=f"{actor.role_label}不能把账号设为{new_role}")


def permissions(actor: User) -> dict:
    """给前端用，决定按钮显隐。"""
    return {
        "can_create_user": can_create(actor),
        "creatable_roles": creatable_roles(actor),
        "rank": rank(actor.role_label),
    }
