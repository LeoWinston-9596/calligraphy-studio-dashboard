"""学员看板（规格书 §5.1）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..balance import (
    account_balance, balance_mode, bulk_student_balance, latest_course_batch, used_lessons_map,
)
from ..db import get_db
from ..editlog import apply_update, logs_for, record_edit
from ..exporter import build_portfolio_html
from ..models import Artwork, CourseAccount, Student, StudentClassTeacher, User
from ..security import current_user
from ..teachers import bulk_student_teachers, class_teachers_for, student_teachers
from ..utils import date_str, dumps, dt_str, edit_badge, loads, loads_list, split_classes

router = APIRouter(prefix="/api/students", tags=["students"])

# 跟进人不在这里改 —— 它按班级存，走 PATCH /{id}/class-teachers
EDITABLE_FIELDS = [
    "name", "student_no", "gender", "phone", "phone_identity", "alt_phone",
    "alt_phone_identity", "birthday", "grade", "school", "address", "source",
    "manager", "tags", "remark", "status",
]


def student_brief(st: Student, bal: dict | None = None,
                  teachers: list[str] | None = None) -> dict:
    return {
        "id": st.id,
        "student_no": st.student_no,
        "name": st.name,
        "phone": st.phone,
        "classes": loads_list(st.classes),
        "grade": st.grade,
        "follow_up_persons": teachers if teachers is not None else [],
        "status": st.status,
        "edit_count": st.edit_count or 0,
        "edit_badge": edit_badge(st.edit_count or 0),
        "balance": bal,
    }


@router.get("")
def list_students(
    q: str = Query("", description="姓名/学号/手机号 模糊搜索"),
    class_name: str = Query(""),
    course_name: str = Query(""),
    follow_up_person: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    query = db.query(Student)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Student.name.like(like),
                                 Student.student_no.like(like),
                                 Student.phone.like(like)))
    if class_name:
        query = query.filter(Student.classes.like(f"%{class_name}%"))
    if follow_up_person:
        # 跟进人按班级存，命中任一班级即算这位老师的学员
        like = f'%"{follow_up_person}"%'
        sub = (db.query(StudentClassTeacher.student_id)
                 .filter(StudentClassTeacher.teachers.like(like)).subquery())
        query = query.filter(Student.id.in_(sub))
    if course_name:
        sub = (db.query(CourseAccount.student_id)
                 .filter(CourseAccount.course_name == course_name).subquery())
        query = query.filter(Student.id.in_(sub))

    total = query.count()
    rows = (query.order_by(Student.status, Student.name)
                 .offset((page - 1) * page_size).limit(page_size).all())
    ids = [r.id for r in rows]
    balances = bulk_student_balance(db, ids)
    teachers = bulk_student_teachers(db, ids)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "mode": balance_mode(db),
        "items": [student_brief(r, balances.get(r.id), teachers.get(r.id, [])) for r in rows],
    }


@router.get("/{student_id}")
def student_detail(student_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="学员不存在")
    mode = balance_mode(db)
    batch = latest_course_batch(db)
    used_map = used_lessons_map(db, [st.id], batch.imported_at if batch else None)
    accounts = db.query(CourseAccount).filter(CourseAccount.student_id == st.id).all()

    # 该生涉及的全部班级：学员名单里的 ∪ 课时账户里的
    class_names: list[str] = []
    for cls in loads_list(st.classes):
        if cls and cls not in class_names:
            class_names.append(cls)
    for acc in accounts:
        for cls in split_classes(acc.class_name):
            if cls and cls not in class_names:
                class_names.append(cls)

    rows = class_teachers_for(db, st.id)
    for cls in rows:
        if cls and cls not in class_names:
            class_names.append(cls)

    class_teachers = []
    for cls in class_names:
        row = rows.get(cls)
        class_teachers.append({
            "class_name": cls,
            "teachers": loads_list(row.teachers) if row else [],
            "course_name": next((a.course_name for a in accounts
                                 if cls in split_classes(a.class_name)), ""),
            "edit_count": (row.edit_count or 0) if row else 0,
            "edit_badge": edit_badge((row.edit_count or 0) if row else 0),
            "updated_by": (row.updated_by_name or "") if row else "",
        })

    return {
        "id": st.id,
        "student_no": st.student_no,
        "name": st.name,
        "gender": st.gender,
        "phone": st.phone,
        "phone_identity": st.phone_identity,
        "alt_phone": st.alt_phone,
        "alt_phone_identity": st.alt_phone_identity,
        "birthday": st.birthday,
        "age": st.age,
        "grade": st.grade,
        "school": st.school,
        "address": st.address,
        "source": st.source,
        "follow_up_persons": student_teachers(db, st.id),
        "class_teachers": class_teachers,
        "manager": st.manager,
        "tags": st.tags,
        "remark": st.remark,
        "classes": loads_list(st.classes),
        "status": st.status,
        "created_by": st.created_by,
        "created_time": st.created_time,
        "extra": loads(st.extra_json, {}),
        "edit_count": st.edit_count or 0,
        "edit_badge": edit_badge(st.edit_count or 0),
        "mode": mode,
        "accounts": [account_out(a, used_map, mode, batch) for a in accounts],
        "total_balance": bulk_student_balance(db, [st.id]).get(st.id),
    }


def account_out(acc: CourseAccount, used_map, mode, batch) -> dict:
    bal = account_balance(acc, used_map, mode, batch)
    return {
        "id": acc.id,
        "course_name": acc.course_name,
        "course_type": acc.course_type,
        "class_name": acc.class_name,
        "purchased": acc.purchased,
        "gifted": acc.gifted,
        "consumed": acc.consumed,
        "refunded": acc.refunded,
        "over_used": acc.over_used,
        "consumed_amount": acc.consumed_amount,
        "remaining_amount": acc.remaining_amount,
        "absent_count": acc.absent_count,
        "expire_date": date_str(acc.expire_date),
        "suspend_time": acc.suspend_time,
        "resume_time": acc.resume_time,
        "suspend_remark": acc.suspend_remark,
        "balance": bal,
    }


@router.patch("/{student_id}")
def update_student(student_id: int, payload: dict = Body(...),
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="学员不存在")
    updates = {k: (str(v).strip() if v is not None else "")
               for k, v in payload.items() if k in EDITABLE_FIELDS}
    if "classes" in payload:
        updates["classes"] = dumps(split_classes(payload["classes"])
                                   if isinstance(payload["classes"], str)
                                   else list(payload["classes"] or []))
    changes = apply_update(db, st, "student", updates, user)
    db.commit()
    return {"ok": True, "changed": changes, "edit_count": st.edit_count or 0,
            "edit_badge": edit_badge(st.edit_count or 0)}


@router.patch("/{student_id}/class-teachers")
def set_class_teachers(student_id: int, class_name: str = Body(...),
                       teachers: list[str] = Body(...),
                       db: Session = Depends(get_db), user: User = Depends(current_user)):
    """设置某个学员在某个班级的跟进人（可多选）。

    留痕挂在学员身上，字段名带班级，这样点学员卡的角标就能看到
    「谁在哪个班把跟进人从什么改成了什么」。
    """
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="学员不存在")
    class_name = (class_name or "").strip()
    if not class_name:
        raise HTTPException(status_code=400, detail="班级不能为空")

    cleaned: list[str] = []
    for name in teachers or []:
        name = str(name).strip()
        if name and name not in cleaned:
            cleaned.append(name)

    row = (db.query(StudentClassTeacher)
             .filter(StudentClassTeacher.student_id == student_id,
                     StudentClassTeacher.class_name == class_name)
             .first())
    if row is None:
        row = StudentClassTeacher(student_id=student_id, class_name=class_name,
                                  teachers=dumps([]), import_teacher="", edit_count=0)
        db.add(row)
        db.flush()

    old = loads_list(row.teachers)
    if old == cleaned:
        return {"ok": True, "changed": [], "teachers": cleaned,
                "edit_count": row.edit_count or 0,
                "edit_badge": edit_badge(row.edit_count or 0)}

    row.teachers = dumps(cleaned)
    row.edit_count = (row.edit_count or 0) + 1
    row.updated_by = user.id
    row.updated_by_name = user.name or user.username

    changes = [{
        "field": "class_teachers",
        "field_label": f"跟进人（{class_name}）",
        "old": old,
        "new": cleaned,
    }]
    # 角标记在学员卡上；这条记录本身已在上面手工累加过 edit_count，故 bump=False
    record_edit(db, st, "student", changes, user)
    db.commit()
    return {"ok": True, "changed": changes, "teachers": cleaned,
            "edit_count": row.edit_count or 0,
            "edit_badge": edit_badge(row.edit_count or 0),
            "student_edit_count": st.edit_count or 0,
            "student_edit_badge": edit_badge(st.edit_count or 0),
            "follow_up_persons": student_teachers(db, student_id)}


@router.get("/{student_id}/logs")
def student_logs(student_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return logs_for(db, "student", student_id)


@router.get("/{student_id}/portfolio", response_class=HTMLResponse)
def portfolio(student_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """导出该生作品集：自包含单页 HTML，手机可看、打印即 PDF。"""
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="学员不存在")
    arts = (db.query(Artwork)
              .filter(Artwork.student_id == student_id, Artwork.deleted == False)  # noqa: E712
              .order_by(Artwork.lesson_date.desc(), Artwork.id.desc()).all())
    html = build_portfolio_html(st, arts)
    filename = f"{st.name or st.student_no or student_id}-作品集.html"
    return HTMLResponse(html, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{_urlquote(filename)}",
    })


def _urlquote(text: str) -> str:
    from urllib.parse import quote
    return quote(text)


@router.get("/{student_id}/timeline")
def timeline(student_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """作品时间轴（倒序）。"""
    from .artworks import artwork_out
    arts = (db.query(Artwork)
              .filter(Artwork.student_id == student_id, Artwork.deleted == False)  # noqa: E712
              .order_by(Artwork.lesson_date.desc(), Artwork.created_at.desc()).all())
    return [artwork_out(a) for a in arts]
