"""老师 ↔ 班级 的自动匹配。

导入表里的「跟进人」就是带班老师，所以老师负责哪些班可以直接从数据推导出来。
权威来源是 StudentClassTeacher（按 (学员, 班级) 存的跟进人列表），
它既包含导入值，也包含手工补的老师 —— 所以手工维护的多老师关系同样能带出班级。

账号开启「自动跟随导入表格」后，以后在教务 App 里新开的班，只要跟进人还是这位老师，
导入之后就会自动出现在他的「我的班级」里 —— 不需要回来手动勾选。
一个账号可以对应表格里的多个名字（身份），班级取并集。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Student, StudentClassTeacher, User
from .utils import loads_list, s


def teacher_class_map(db: Session) -> dict[str, list[str]]:
    """{老师名: [班级, ...]}。"""
    out: dict[str, set[str]] = {}
    for class_name, teachers in db.query(StudentClassTeacher.class_name,
                                         StudentClassTeacher.teachers).all():
        if not class_name:
            continue
        for name in loads_list(teachers):
            if name:
                out.setdefault(name, set()).add(class_name)
    return {k: sorted(v) for k, v in sorted(out.items()) if v}


def all_teacher_names(db: Session) -> list[str]:
    """跟进人多选的候选名单：出现过的所有老师名 ∪ 各账号已绑定的身份。"""
    names: set[str] = set()
    for _, teachers in db.query(StudentClassTeacher.class_name,
                                StudentClassTeacher.teachers).all():
        names.update(x for x in loads_list(teachers) if x)
    for (raw,) in db.query(User.teacher_names).all():
        names.update(x for x in loads_list(raw) if x)
    # 导入原始值兜底：还没建过 StudentClassTeacher 行的老师也要能选到
    for (person,) in db.query(Student.follow_up_person).distinct().all():
        if s(person):
            names.add(s(person))
    return sorted(names)


def teacher_summary(db: Session) -> list[dict]:
    """老师名单 + 带班数 + 学员数，供注册账号时选择身份。"""
    cmap = teacher_class_map(db)
    # 学员数按去重的 student_id 统计
    per_teacher: dict[str, set[int]] = {}
    for student_id, teachers in db.query(StudentClassTeacher.student_id,
                                         StudentClassTeacher.teachers).all():
        for name in set(loads_list(teachers)):
            if name and student_id:
                per_teacher.setdefault(name, set()).add(student_id)

    return [{
        "name": name,
        "classes": classes,
        "class_count": len(classes),
        "student_count": len(per_teacher.get(name, ())),
    } for name, classes in cmap.items()]


def user_identities(user: User) -> list[str]:
    """账号对应的老师名（多身份）。兼容尚未迁移的旧单值字段。"""
    names = [x for x in loads_list(user.teacher_names) if x]
    if not names and (user.teacher_name or "").strip():
        names = [user.teacher_name.strip()]
    return names


def resolve_classes(db: Session, user: User) -> list[str]:
    """账号实际生效的「我的班级」。

    自动模式下跟随导入数据，多个身份取班级并集；手动模式下用勾选的班级。
    """
    if not user.auto_bind_classes:
        return loads_list(user.class_bindings)

    identities = user_identities(user) or [(user.name or "").strip()]
    cmap = teacher_class_map(db)
    classes: set[str] = set()
    for name in identities:
        if name:
            classes.update(cmap.get(name, []))
    return sorted(classes)


def match_teacher_names(db: Session, name: str) -> list[str]:
    """把账号姓名对到导入表里的老师名，返回所有匹配到的身份（注册时自动勾选）。

    支持「张老师」「张」「张三」这类写法差异：先精确匹配，再去掉「老师」后缀比较，
    最后退到前缀匹配。匹配不到返回空列表。
    """
    key = (name or "").strip()
    if not key:
        return []
    candidates = list(teacher_class_map(db).keys())
    if key in candidates:
        return [key]

    stripped = key.removesuffix("老师").strip()
    if not stripped:
        return []

    exact = [c for c in candidates if c.removesuffix("老师").strip() == stripped]
    if exact:
        return exact
    return [c for c in candidates
            if c.startswith(stripped) or stripped.startswith(c.removesuffix("老师"))]


def student_teachers(db: Session, student_id: int) -> list[str]:
    """学员层的跟进人汇总（所有班级的并集）。"""
    names: set[str] = set()
    for (teachers,) in db.query(StudentClassTeacher.teachers).filter(
            StudentClassTeacher.student_id == student_id).all():
        names.update(x for x in loads_list(teachers) if x)
    return sorted(names)


def bulk_student_teachers(db: Session, student_ids: list[int]) -> dict[int, list[str]]:
    """列表页批量版本，避免 N+1。"""
    if not student_ids:
        return {}
    out: dict[int, set[str]] = {sid: set() for sid in student_ids}
    rows = (db.query(StudentClassTeacher.student_id, StudentClassTeacher.teachers)
              .filter(StudentClassTeacher.student_id.in_(student_ids)).all())
    for student_id, teachers in rows:
        out.setdefault(student_id, set()).update(x for x in loads_list(teachers) if x)
    return {k: sorted(v) for k, v in out.items()}


def class_teachers_for(db: Session, student_id: int) -> dict[str, StudentClassTeacher]:
    rows = (db.query(StudentClassTeacher)
              .filter(StudentClassTeacher.student_id == student_id).all())
    return {r.class_name: r for r in rows}
