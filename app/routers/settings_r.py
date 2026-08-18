"""设置页（规格书 §5.5）+ 评语模板库（§5.2）+ 全站元数据。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..backup import backup_status, run_backup
from ..balance import all_settings, balance_mode, set_setting
from ..db import get_db
from ..editlog import apply_update, logs_for
from ..importer import data_asof
from ..models import ClassCourseMap, CourseAccount, EvalTemplate, Student, User
from ..security import current_user
from ..utils import edit_badge, loads_list

router = APIRouter(prefix="/api", tags=["settings"])

INT_KEYS = ("renew_threshold", "expire_days", "absent_threshold")
CATEGORIES = ("书法", "美术", "通用")


# ------------------------------------------------------------------ 设置

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"settings": all_settings(db), "backup": backup_status(db)}


@router.patch("/settings")
def patch_settings(payload: dict = Body(...), db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    if "balance_mode" in payload:
        mode = payload["balance_mode"]
        if mode not in ("imported", "estimated"):
            raise HTTPException(status_code=400, detail="口径只能是 imported / estimated")
        set_setting(db, "balance_mode", mode)
    for key in INT_KEYS:
        if key in payload:
            try:
                value = int(payload[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} 必须是整数")
            if value < 0:
                raise HTTPException(status_code=400, detail=f"{key} 不能为负数")
            set_setting(db, key, str(value))
    db.commit()
    return {"settings": all_settings(db)}


@router.post("/backup/run")
async def manual_backup(db: Session = Depends(get_db), _: User = Depends(current_user)):
    result = await asyncio.to_thread(run_backup, "manual")
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("message", "备份失败"))
    return {**result, "status": backup_status(db)}


# ------------------------------------------------------------------ 元数据

@router.get("/meta")
def meta(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """顶栏数据截止时间、备份提醒、筛选项、班级→课程映射。"""
    classes = sorted({c for (c,) in db.query(ClassCourseMap.class_name).distinct() if c})
    if not classes:
        seen: set[str] = set()
        for (raw,) in db.query(Student.classes).all():
            seen.update(loads_list(raw))
        classes = sorted(x for x in seen if x)
    courses = sorted({c for (c,) in db.query(CourseAccount.course_name).distinct() if c})
    from ..teachers import all_teacher_names
    persons = all_teacher_names(db)
    cmap = {}
    for row in db.query(ClassCourseMap).order_by(ClassCourseMap.hits.desc()).all():
        cmap.setdefault(row.class_name, row.course_name)

    from ..config import HTTPS_PORT
    from ..roles import permissions
    from ..teachers import resolve_classes, user_identities
    return {
        "asof": data_asof(db),
        "backup": backup_status(db),
        "balance_mode": balance_mode(db),
        "classes": classes,
        "courses": courses,
        "follow_up_persons": persons,
        "class_course_map": cmap,
        # 自动模式下跟随导入表格，新导入的班级会自动出现，无需回来手选
        "my_classes": resolve_classes(db, user),
        "auto_bind_classes": bool(user.auto_bind_classes),
        "teacher_names": user_identities(user),
        "permissions": permissions(user),
        "https_port": HTTPS_PORT,
    }


@router.get("/classes/{class_name}/students")
def class_students(class_name: str, db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    """老师工作台：班级学员九宫格。"""
    from ..balance import bulk_student_balance
    ids = {sid for (sid,) in db.query(CourseAccount.student_id)
           .filter(CourseAccount.class_name == class_name).distinct() if sid}
    rows = db.query(Student).filter(Student.classes.like(f"%{class_name}%")).all()
    ids.update(r.id for r in rows)
    students = db.query(Student).filter(Student.id.in_(ids)).order_by(Student.name).all() if ids else []
    balances = bulk_student_balance(db, [s.id for s in students])
    course = db.query(ClassCourseMap).filter(ClassCourseMap.class_name == class_name) \
               .order_by(ClassCourseMap.hits.desc()).first()
    return {
        "class_name": class_name,
        "course_name": course.course_name if course else "",
        "count": len(students),
        "items": [{
            "id": s.id, "name": s.name, "student_no": s.student_no,
            "balance": balances.get(s.id),
        } for s in students],
    }


# ------------------------------------------------------------------ 评语模板

@router.get("/eval-templates")
def list_templates(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = (db.query(EvalTemplate).filter(EvalTemplate.deleted == False)  # noqa: E712
              .order_by(EvalTemplate.category, EvalTemplate.sort, EvalTemplate.id).all())
    return [{
        "id": t.id, "category": t.category, "text": t.text, "sort": t.sort,
        "edit_count": t.edit_count or 0, "edit_badge": edit_badge(t.edit_count or 0),
    } for t in rows]


@router.post("/eval-templates")
def create_template(category: str = Body(...), text: str = Body(...), sort: int = Body(0),
                    db: Session = Depends(get_db), _: User = Depends(current_user)):
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="分类只能是 书法/美术/通用")
    if not text.strip():
        raise HTTPException(status_code=400, detail="模板内容不能为空")
    t = EvalTemplate(category=category, text=text.strip(), sort=sort, edit_count=0)
    db.add(t)
    db.commit()
    return {"id": t.id, "category": t.category, "text": t.text, "sort": t.sort,
            "edit_count": 0, "edit_badge": ""}


@router.patch("/eval-templates/{template_id}")
def update_template(template_id: int, payload: dict = Body(...),
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(EvalTemplate, template_id)
    if not t or t.deleted:
        raise HTTPException(status_code=404, detail="模板不存在")
    updates = {}
    if "category" in payload and payload["category"] in CATEGORIES:
        updates["category"] = payload["category"]
    if "text" in payload:
        if not str(payload["text"]).strip():
            raise HTTPException(status_code=400, detail="模板内容不能为空")
        updates["text"] = str(payload["text"]).strip()
    if "sort" in payload:
        try:
            updates["sort"] = int(payload["sort"])
        except (TypeError, ValueError):
            pass
    changes = apply_update(db, t, "eval_template", updates, user)
    db.commit()
    return {"ok": True, "changed": changes, "edit_count": t.edit_count or 0,
            "edit_badge": edit_badge(t.edit_count or 0)}


@router.delete("/eval-templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    t = db.get(EvalTemplate, template_id)
    if not t or t.deleted:
        raise HTTPException(status_code=404, detail="模板不存在")
    from ..editlog import record_edit
    t.deleted = True
    record_edit(db, t, "eval_template",
                [{"field": "deleted", "field_label": "删除状态", "old": False, "new": True}],
                user, action="delete")
    db.commit()
    return {"ok": True}


@router.get("/eval-templates/{template_id}/logs")
def template_logs(template_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return logs_for(db, "eval_template", template_id)


DEFAULT_TEMPLATES = [
    ("书法", "今天的笔画起收到位，结构比上次更稳，继续保持。"),
    ("书法", "运笔速度偏快，注意提按变化，写完记得回看整体章法。"),
    ("书法", "字距行距把握得不错，个别字重心略偏，下次注意中轴线。"),
    ("书法", "临帖认真，字形接近范本，建议加强横竖的力度对比。"),
    ("美术", "构图饱满，主体突出，色彩搭配有想法。"),
    ("美术", "线条流畅，造型准确，明暗关系可以再拉开一些。"),
    ("美术", "上色均匀，画面干净，建议丰富背景层次。"),
    ("美术", "观察仔细，细节刻画到位，继续保持这份耐心。"),
    ("通用", "今天课堂表现积极，作业完成质量高。"),
    ("通用", "有明显进步，继续加油！"),
    ("通用", "注意坐姿和握笔姿势，回家可再练习 15 分钟。"),
    ("通用", "本节课状态一般，下次课前请提前准备好工具。"),
]


def seed_templates(db: Session) -> None:
    if db.query(EvalTemplate).count() == 0:
        for i, (cat, text) in enumerate(DEFAULT_TEMPLATES):
            db.add(EvalTemplate(category=cat, text=text, sort=i, edit_count=0))
        db.commit()
