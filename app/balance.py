"""剩余课时两种口径（规格书 §6）。

导入口径：直接用 CourseAccount.remaining_imported。
估算口径：remaining_imported − 该学员该课程在最近一次「报读课程」导入之后的评价课次数。
          评价课次数 = COUNT(DISTINCT lesson_date)。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from .config import DEFAULT_SETTINGS
from .models import AppSetting, Artwork, ClassCourseMap, CourseAccount, ImportBatch


# ---------- 设置项 ----------

def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row and row.value is not None:
        return row.value
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = str(value)
    else:
        db.add(AppSetting(key=key, value=str(value)))


def all_settings(db: Session) -> dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    for row in db.query(AppSetting).all():
        if row.value is not None:
            out[row.key] = row.value
    return out


def get_int_setting(db: Session, key: str, fallback: int) -> int:
    try:
        return int(float(get_setting(db, key)))
    except (TypeError, ValueError):
        return fallback


def balance_mode(db: Session) -> str:
    mode = get_setting(db, "balance_mode")
    return mode if mode in ("imported", "estimated") else "estimated"


# ---------- 批次与班级映射 ----------

def latest_course_batch(db: Session) -> ImportBatch | None:
    return (db.query(ImportBatch)
              .filter(ImportBatch.file_type == "courses")
              .order_by(ImportBatch.imported_at.desc(), ImportBatch.id.desc())
              .first())


def class_course_map(db: Session) -> dict[str, str]:
    """班级 → 课程（同班多课程时取出现次数最多的）。"""
    out: dict[str, tuple[str, int]] = {}
    for row in db.query(ClassCourseMap).all():
        cur = out.get(row.class_name)
        if cur is None or (row.hits or 0) > cur[1]:
            out[row.class_name] = (row.course_name, row.hits or 0)
    return {k: v[0] for k, v in out.items()}


def course_of_class(db: Session, class_name: str) -> str | None:
    return class_course_map(db).get(class_name)


# ---------- 评价课次统计 ----------

def used_lessons_map(
    db: Session,
    student_ids: Iterable[int] | None,
    since: datetime | None,
) -> dict[tuple[int, str], set]:
    """返回 {(student_id, course_name): {lesson_date, ...}}。

    since 为最近一次报读课程导入时间；仅统计该时间之后创建的评价。
    """
    q = db.query(Artwork).filter(Artwork.deleted == False)  # noqa: E712
    ids = list(student_ids) if student_ids is not None else None
    if ids is not None:
        if not ids:
            return {}
        q = q.filter(Artwork.student_id.in_(ids))
    if since is not None:
        q = q.filter(Artwork.created_at > since)

    cmap = class_course_map(db)
    out: dict[tuple[int, str], set] = {}
    for art in q.all():
        course = art.course_name or cmap.get(art.class_name or "")
        if not course or art.lesson_date is None or art.student_id is None:
            continue
        out.setdefault((art.student_id, course), set()).add(art.lesson_date)
    return out


def account_balance(
    account: CourseAccount,
    used_map: dict[tuple[int, str], set],
    mode: str,
    batch: ImportBatch | None,
) -> dict:
    """单个课时账户的两种口径结果 + 展开说明文案。"""
    imported = int(account.remaining_imported or 0)
    used_dates = used_map.get((account.student_id, account.course_name), set())
    used = len(used_dates)
    estimated = imported - used
    import_day = ""
    if batch and batch.imported_at:
        import_day = f"{batch.imported_at.month}月{batch.imported_at.day}日"
    detail = (f"导入时 {imported}"
              + (f"（{import_day}）" if import_day else "")
              + f" − 评价 {used} 次 = 约 {estimated}")
    current = estimated if mode == "estimated" else imported
    return {
        "imported": imported,
        "estimated": estimated,
        "used_lessons": used,
        "used_dates": sorted(d.isoformat() for d in used_dates),
        "mode": mode,
        "current": current,
        "display": (f"约 {estimated} 课时" if mode == "estimated" else f"{imported} 课时"),
        "detail": detail,
    }


def student_total_balance(db: Session, student_id: int, mode: str | None = None) -> dict:
    """学员所有课程账户的合计余额（列表页角标用）。"""
    mode = mode or balance_mode(db)
    batch = latest_course_batch(db)
    used_map = used_lessons_map(db, [student_id], batch.imported_at if batch else None)
    accounts = db.query(CourseAccount).filter(CourseAccount.student_id == student_id).all()
    imported = sum(int(a.remaining_imported or 0) for a in accounts)
    estimated = sum(account_balance(a, used_map, mode, batch)["estimated"] for a in accounts)
    current = estimated if mode == "estimated" else imported
    return {
        "imported": imported,
        "estimated": estimated,
        "current": current,
        "mode": mode,
        "display": (f"约 {estimated} 课时" if mode == "estimated" else f"{imported} 课时"),
    }


def bulk_student_balance(db: Session, student_ids: list[int], mode: str | None = None) -> dict[int, dict]:
    """批量版本，避免列表页 N+1。"""
    mode = mode or balance_mode(db)
    batch = latest_course_batch(db)
    used_map = used_lessons_map(db, student_ids, batch.imported_at if batch else None)
    if not student_ids:
        return {}
    accounts = (db.query(CourseAccount)
                  .filter(CourseAccount.student_id.in_(student_ids))
                  .all())
    agg: dict[int, dict] = {sid: {"imported": 0, "estimated": 0} for sid in student_ids}
    for acc in accounts:
        bal = account_balance(acc, used_map, mode, batch)
        slot = agg.setdefault(acc.student_id, {"imported": 0, "estimated": 0})
        slot["imported"] += bal["imported"]
        slot["estimated"] += bal["estimated"]
    out = {}
    for sid, v in agg.items():
        current = v["estimated"] if mode == "estimated" else v["imported"]
        out[sid] = {
            **v,
            "current": current,
            "mode": mode,
            "display": (f"约 {v['estimated']} 课时" if mode == "estimated" else f"{v['imported']} 课时"),
        }
    return out
