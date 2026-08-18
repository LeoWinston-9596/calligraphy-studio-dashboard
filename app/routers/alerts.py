"""课时提醒看板（规格书 §5.3）：续费预警 / 到期预警 / 缺课关注。"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..balance import (
    account_balance, balance_mode, get_int_setting, latest_course_batch, used_lessons_map,
)
from ..db import get_db
from ..editlog import apply_update, logs_for
from ..models import CourseAccount, FollowUp, Student, User
from ..security import current_user
from ..utils import date_str, edit_badge, split_classes

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

TABS = ("renew", "expire", "absent")
TAB_LABELS = {"renew": "续费预警", "expire": "到期预警", "absent": "缺课关注"}


def _follow_map(db: Session, alert_type: str) -> dict[int, FollowUp]:
    rows = db.query(FollowUp).filter(FollowUp.alert_type == alert_type).all()
    return {r.course_account_id: r for r in rows}


@router.get("")
def list_alerts(tab: str = Query("renew"), db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    if tab not in TABS:
        raise HTTPException(status_code=400, detail="未知的提醒类型")
    mode = balance_mode(db)
    batch = latest_course_batch(db)
    used_map = used_lessons_map(db, None, batch.imported_at if batch else None)

    renew_threshold = get_int_setting(db, "renew_threshold", 3)
    expire_days = get_int_setting(db, "expire_days", 14)
    absent_threshold = get_int_setting(db, "absent_threshold", 2)
    today = date.today()
    limit_date = today + timedelta(days=expire_days)

    accounts = db.query(CourseAccount).all()
    follows = _follow_map(db, tab)

    # 跟进人按 (学员, 班级) 存，这里一次性取出来避免 N+1
    from ..models import StudentClassTeacher
    from ..utils import loads_list
    teacher_rows = db.query(StudentClassTeacher.student_id,
                            StudentClassTeacher.class_name,
                            StudentClassTeacher.teachers).all()
    teacher_index = {(sid, cls): loads_list(t) for sid, cls, t in teacher_rows}

    items = []
    for acc in accounts:
        bal = account_balance(acc, used_map, mode, batch)
        if tab == "renew":
            if bal["current"] > renew_threshold:
                continue
        elif tab == "expire":
            if not acc.expire_date or not (today <= acc.expire_date <= limit_date):
                continue
        else:
            if (acc.absent_count or 0) < absent_threshold:
                continue

        fu = follows.get(acc.id)
        persons: list[str] = []
        for cls in split_classes(acc.class_name):
            for name in teacher_index.get((acc.student_id, cls), []):
                if name not in persons:
                    persons.append(name)
        if not persons and acc.follow_up_person:
            persons = [acc.follow_up_person]

        items.append({
            "course_account_id": acc.id,
            "student_id": acc.student_id,
            "student_no": acc.student_no,
            "student_name": acc.student_name,
            "course_name": acc.course_name,
            "class_name": acc.class_name,
            "follow_up_persons": persons,
            "absent_count": acc.absent_count or 0,
            "expire_date": date_str(acc.expire_date),
            "days_to_expire": (acc.expire_date - today).days if acc.expire_date else None,
            "balance": bal,
            "follow_status": fu.status if fu else "待跟进",
            "follow_id": fu.id if fu else None,
            "follow_note": fu.note if fu else "",
            "follow_updated_by": fu.updated_by_name if fu else "",
            "follow_updated_at": fu.updated_at.strftime("%Y-%m-%d %H:%M") if fu and fu.updated_at else "",
            "edit_count": fu.edit_count if fu else 0,
            "edit_badge": edit_badge(fu.edit_count if fu else 0),
        })

    if tab == "renew":
        items.sort(key=lambda x: x["balance"]["current"])
    elif tab == "expire":
        items.sort(key=lambda x: x["days_to_expire"] if x["days_to_expire"] is not None else 999)
    else:
        items.sort(key=lambda x: -x["absent_count"])

    return {
        "tab": tab,
        "tab_label": TAB_LABELS[tab],
        "mode": mode,
        "thresholds": {
            "renew_threshold": renew_threshold,
            "expire_days": expire_days,
            "absent_threshold": absent_threshold,
        },
        "count": len(items),
        "items": items,
    }


@router.get("/counts")
def counts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {tab: list_alerts(tab, db, user)["count"] for tab in TABS}


@router.post("/follow")
def mark_follow(course_account_id: int = Body(...), alert_type: str = Body(...),
                status: str = Body("已跟进"), note: str = Body(""),
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    if alert_type not in TABS:
        raise HTTPException(status_code=400, detail="未知的提醒类型")
    if status not in ("待跟进", "已跟进"):
        raise HTTPException(status_code=400, detail="未知的跟进状态")
    acc = db.get(CourseAccount, course_account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="课时账户不存在")

    fu = (db.query(FollowUp)
            .filter(FollowUp.course_account_id == course_account_id,
                    FollowUp.alert_type == alert_type)
            .first())
    if fu is None:
        fu = FollowUp(student_id=acc.student_id, course_account_id=course_account_id,
                      alert_type=alert_type, status=status, note=note,
                      edit_count=0, updated_by=user.id,
                      updated_by_name=user.name or user.username)
        db.add(fu)
        db.commit()
        return {"ok": True, "status": fu.status, "edit_count": 0, "edit_badge": ""}

    apply_update(db, fu, "follow_up", {"status": status, "note": note}, user)
    db.commit()
    return {"ok": True, "status": fu.status, "edit_count": fu.edit_count or 0,
            "edit_badge": edit_badge(fu.edit_count or 0)}


@router.get("/follow/{follow_id}/logs")
def follow_logs(follow_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return logs_for(db, "follow_up", follow_id)
