"""编辑留痕（规格书 §7）—— 一切可编辑对象共用。

导入覆盖不走这里，因此不会触发角标。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import EditLog, User
from .utils import dumps, loads_list

# 字段的中文显示名，用于编辑记录弹窗
FIELD_LABELS = {
    # Student
    "name": "姓名", "student_no": "学号", "gender": "性别", "phone": "手机号",
    "phone_identity": "手机号身份", "alt_phone": "备用手机号",
    "alt_phone_identity": "备用手机号身份", "birthday": "出生日期", "grade": "年级",
    "school": "学校", "address": "住址", "source": "来源",
    "follow_up_person": "跟进人", "class_teachers": "班级跟进人",
    "manager": "学管师", "tags": "标签",
    "remark": "备注", "classes": "所在班级", "status": "状态", "age": "年龄",
    # Artwork
    "lesson_date": "上课日期", "class_name": "班级", "course_name": "课程",
    "eval_type": "评价方式", "eval_text": "评价文字", "eval_audio_path": "语音评价",
    "rating": "评级", "photos": "作品照片", "deleted": "删除状态",
    "transcript": "语音文字稿",
    # FollowUp
    "note": "跟进备注",
    # EvalTemplate
    "category": "分类", "text": "模板内容", "sort": "排序",
}


def _norm(value: Any) -> Any:
    """转成可比较、可 JSON 化的形式。"""
    if isinstance(value, (datetime,)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def diff_changes(entity, updates: dict[str, Any]) -> list[dict]:
    """比较实体现值与待写入值，返回 [{field, field_label, old, new}]。"""
    changes: list[dict] = []
    for field, new_value in updates.items():
        if not hasattr(entity, field):
            continue
        old_value = _norm(getattr(entity, field))
        new_norm = _norm(new_value)
        if old_value == new_norm:
            continue
        changes.append({
            "field": field,
            "field_label": FIELD_LABELS.get(field, field),
            "old": old_value,
            "new": new_norm,
        })
    return changes


def file_changes(field: str, old_files: list[str], new_files: list[str]) -> list[dict]:
    """图片/音频变更记录文件名增删（规格书 §7）。"""
    added = [f for f in new_files if f not in old_files]
    removed = [f for f in old_files if f not in new_files]
    if not added and not removed:
        return []
    desc = []
    if added:
        desc.append("新增 " + "、".join(_basename(f) for f in added))
    if removed:
        desc.append("删除 " + "、".join(_basename(f) for f in removed))
    return [{
        "field": field,
        "field_label": FIELD_LABELS.get(field, field),
        "old": [_basename(f) for f in old_files],
        "new": [_basename(f) for f in new_files],
        "note": "；".join(desc),
    }]


def _basename(path: str) -> str:
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def record_edit(
    db: Session,
    entity,
    entity_type: str,
    changes: list[dict],
    user: User | None,
    action: str = "update",
    bump: bool = True,
) -> EditLog | None:
    """写一条 EditLog 并把 edit_count += 1。无实际变更时不写、不加角标。"""
    if not changes:
        return None
    if bump and hasattr(entity, "edit_count"):
        entity.edit_count = (entity.edit_count or 0) + 1
    log = EditLog(
        entity_type=entity_type,
        entity_id=entity.id,
        editor_id=user.id if user else None,
        editor_name=(user.name or user.username) if user else "系统",
        action=action,
        changes_json=dumps(changes),
    )
    db.add(log)
    if hasattr(entity, "updated_by"):
        entity.updated_by = user.id if user else None
    if hasattr(entity, "updated_by_name"):
        entity.updated_by_name = (user.name or user.username) if user else "系统"
    return log


def apply_update(db: Session, entity, entity_type: str, updates: dict, user: User | None) -> list[dict]:
    """通用：算 diff → 赋值 → 留痕。返回变更列表。"""
    changes = diff_changes(entity, updates)
    for field, value in updates.items():
        if hasattr(entity, field):
            setattr(entity, field, value)
    record_edit(db, entity, entity_type, changes, user)
    return changes


def logs_for(db: Session, entity_type: str, entity_id: int) -> list[dict]:
    """按时间倒序列出编辑记录。"""
    rows = (db.query(EditLog)
              .filter(EditLog.entity_type == entity_type, EditLog.entity_id == entity_id)
              .order_by(EditLog.edited_at.desc(), EditLog.id.desc())
              .all())
    return [{
        "id": r.id,
        "editor": r.editor_name,
        "edited_at": r.edited_at.strftime("%Y-%m-%d %H:%M:%S") if r.edited_at else "",
        "action": r.action,
        "changes": loads_list(r.changes_json),
    } for r in rows]
