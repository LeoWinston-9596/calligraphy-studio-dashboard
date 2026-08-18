"""Excel 导入（规格书 §4）：4 种格式按列名自动识别，整表覆盖式更新。

- 在读学员名单 (.xls) → Student
- 学生报读课程 (.xls, sheet「报读课程」) → CourseAccount + 班级→课程映射
- 订单导出 (.xlsx) → Order（只读）
- 收支明细 (.xls) → Transaction（只读）

导入覆盖不算编辑，不写 EditLog、不触发角标。
"""
from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from .balance import account_balance, latest_course_batch, used_lessons_map
from .models import (
    ClassCourseMap, CourseAccount, ImportBatch, Order, Student, StudentClassTeacher,
    Transaction, User,
)
from .utils import (
    dumps, is_blank, loads_list, normalize_phone, parse_date, parse_datetime,
    parse_lessons, parse_number, s, split_classes,
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

FILE_TYPES = {
    "students": "在读学员名单",
    "courses": "学生报读课程",
    "orders": "订单导出",
    "transactions": "收支明细",
}

# 各格式的特征列，用于自动识别
SIGNATURES = {
    "courses": {"课程名称", "购买数量", "剩余数量"},
    "students": {"学员姓名", "学号", "所在班级"},
    "orders": {"订单号", "购买项目", "订单状态"},
    "transactions": {"收支项目", "收支类型", "收支金额"},
}

STUDENT_COLS = [
    "学员姓名", "性别", "手机号身份", "手机号", "微信绑定状态", "绑卡状态", "人脸采集状态",
    "备用手机号身份", "备用手机号", "来源", "出生日期", "所在班级", "年龄", "年级", "学号",
    "学校", "跟进人", "学管师", "住址", "标签", "备注", "学员创建人", "创建时间",
]

COURSE_CORE_COLS = [
    "学员姓名", "手机号身份", "手机号", "所在班级", "课程名称", "课程类型", "购买数量",
    "赠送数量", "消耗数量", "退转数量", "剩余数量", "超上数量", "课消金额", "剩余课消金额",
    "缺课次数", "跟进人", "学管师", "到期时间", "停课时间", "复课时间", "停课备注", "学号",
]

ORDER_COLS = [
    "订单号", "流水号（支付/退款）", "学生姓名", "手机号", "订单类型", "购买项目",
    "应收/应退", "实收/实退", "欠费金额", "订单来源", "业绩归属人", "经办人", "创建时间",
    "经办时间", "上次推送时间", "最近支付时间", "先学后付订单状态", "订单状态", "备注",
    "留言", "学生创建人",
]

TXN_COLS = [
    "创建时间", "收支项目", "收支类型", "状态", "收支金额", "支付方式", "收支账户",
    "经办日期", "经办人", "关联订单号", "收付款人", "支付流水号", "交易失败原因", "备注",
    "校区名称",
]


class ImportError_(Exception):
    """导入相关的用户可见错误。"""


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------

def read_excel(path: Path) -> pd.DataFrame:
    """读第一个有效 sheet；「学生报读课程」文件含多余的 hidden sheet，只读『报读课程』。"""
    suffix = path.suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        xl = pd.ExcelFile(path, engine=engine)
    except Exception:
        # 有些导出把 .xls 存成 xlsx/html，退一步让 pandas 自己判断
        xl = pd.ExcelFile(path)
    sheet = xl.sheet_names[0]
    for name in xl.sheet_names:
        if str(name).strip() == "报读课程":
            sheet = name
            break
    df = xl.parse(sheet)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_type(df: pd.DataFrame, filename: str = "") -> str:
    cols = set(df.columns)
    best, best_score = "", 0
    for ftype, sig in SIGNATURES.items():
        score = len(sig & cols)
        if score == len(sig) and score > best_score:
            best, best_score = ftype, score
    if best:
        return best
    # 列名不全时用文件名兜底
    for ftype, label in FILE_TYPES.items():
        if label in filename:
            return ftype
    raise ImportError_("无法识别文件类型：列名与四种已知导出格式都不匹配")


def preview(path: Path, filename: str = "", rows: int = 5) -> dict:
    df = read_excel(path)
    ftype = detect_type(df, filename or path.name)
    head = df.head(rows).where(pd.notna(df.head(rows)), None)
    return {
        "file_type": ftype,
        "file_type_label": FILE_TYPES[ftype],
        "columns": list(df.columns),
        "total_rows": int(len(df)),
        "rows": [[_cell(v) for v in rec] for rec in head.values.tolist()],
        "missing_columns": _missing_columns(ftype, df),
    }


def _cell(v: Any) -> Any:
    if is_blank(v):
        return ""
    if isinstance(v, (datetime, pd.Timestamp)):
        return s(v)
    return s(v)


def _missing_columns(ftype: str, df: pd.DataFrame) -> list[str]:
    expected = {
        "students": STUDENT_COLS,
        "courses": COURSE_CORE_COLS,
        "orders": ORDER_COLS,
        "transactions": TXN_COLS,
    }[ftype]
    return [c for c in expected if c not in df.columns]


def _extra(row: dict, used: list[str]) -> str:
    """规格书未列举的列原样保留。"""
    rest = {k: s(v) for k, v in row.items() if k not in used and not is_blank(v)}
    return dumps(rest)


# --------------------------------------------------------------------------
# 跟进人合并：导入值只占一个「槽位」，手工添加的老师永远保留
# --------------------------------------------------------------------------

def _upsert_class_teacher(db: Session, cache: dict, student_id: int,
                          class_name: str, imported_teacher: str) -> None:
    """把导入的跟进人合并进 (学员, 班级) 的老师列表。

    规则：先摘掉上次导入留下的那个值，再放入本次导入值，其余（手工加的）原样保留。
    这样三件事同时成立 —— 手工维护不被冲掉、导入值变更能正确替换而不是越堆越多、
    重复导入同一文件结果幂等。

    学员表和课程表都会调用这里、共用同一个 import_teacher 槽位，后写的覆盖前一次导入值；
    实际数据里两张表的跟进人一致，冲突可忽略。
    """
    # class_name 允许为空字符串：表示「未分班」的学员级跟进人，否则没班的学员
    # 跟进人会整个丢掉。teacher_class_map 会跳过空班级，不会污染班级列表。
    if not student_id:
        return
    key = (student_id, class_name)
    row = cache.get(key)
    if row is None:
        row = (db.query(StudentClassTeacher)
                 .filter(StudentClassTeacher.student_id == student_id,
                         StudentClassTeacher.class_name == class_name)
                 .first())
        if row is None:
            row = StudentClassTeacher(student_id=student_id, class_name=class_name,
                                      teachers=dumps([]), import_teacher="", edit_count=0)
            db.add(row)
            db.flush()
        cache[key] = row

    old_import = row.import_teacher or ""
    teachers = [t for t in loads_list(row.teachers) if t and t != old_import]
    if imported_teacher and imported_teacher not in teachers:
        teachers.append(imported_teacher)
    row.teachers = dumps(teachers)
    row.import_teacher = imported_teacher


# --------------------------------------------------------------------------
# 学员匹配
# --------------------------------------------------------------------------

class StudentIndex:
    """学号为主键；学号缺失时用 姓名+手机号。"""

    def __init__(self, db: Session):
        self.db = db
        self.by_no: dict[str, Student] = {}
        self.by_name_phone: dict[tuple[str, str], Student] = {}
        for st in db.query(Student).all():
            self._index(st)

    def _index(self, st: Student) -> None:
        if st.student_no:
            self.by_no[st.student_no] = st
        key = (st.name or "", normalize_phone(st.phone))
        self.by_name_phone[key] = st

    def add(self, st: Student) -> None:
        self._index(st)

    def find(self, student_no: str, name: str, phone: str) -> Student | None:
        if student_no and student_no in self.by_no:
            return self.by_no[student_no]
        key = (name or "", normalize_phone(phone))
        if key[0] and key[1]:
            return self.by_name_phone.get(key)
        return None


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------

def run_import(db: Session, path: Path, filename: str, user: User | None,
               file_type: str | None = None) -> dict:
    df = read_excel(path)
    ftype = file_type or detect_type(df, filename)
    batch = ImportBatch(
        file_type=ftype,
        filename=filename,
        imported_by=user.id if user else None,
        imported_by_name=(user.name or user.username) if user else "系统",
        imported_at=datetime.now(),
        row_count=int(len(df)),
    )
    db.add(batch)
    db.flush()

    if ftype == "students":
        report = _import_students(db, df, batch)
    elif ftype == "courses":
        report = _import_courses(db, df, batch)
    elif ftype == "orders":
        report = _import_orders(db, df, batch)
    else:
        report = _import_transactions(db, df, batch)

    report["file_type"] = ftype
    report["file_type_label"] = FILE_TYPES[ftype]
    report["filename"] = filename
    report["imported_at"] = batch.imported_at.strftime("%Y-%m-%d %H:%M:%S")
    report["batch_id"] = batch.id
    batch.summary = dumps(report)
    db.commit()
    return report


# --------------------------------------------------------------------------
# 4.1 在读学员名单 → Student
# --------------------------------------------------------------------------

def _import_students(db: Session, df: pd.DataFrame, batch: ImportBatch) -> dict:
    index = StudentIndex(db)
    created = updated = 0
    skipped: list[dict] = []
    seen_ids: set[int] = set()
    sct_cache: dict = {}

    for i, raw in enumerate(df.to_dict("records")):
        excel_row = i + 2  # 含表头
        name = s(raw.get("学员姓名"))
        student_no = s(raw.get("学号"))
        phone = s(raw.get("手机号"))
        if not name and not student_no:
            skipped.append({"row": excel_row, "reason": "缺少学员姓名与学号"})
            continue

        st = index.find(student_no, name, phone)
        is_new = st is None
        if is_new:
            st = Student()
            db.add(st)

        st.student_no = student_no or st.student_no
        st.name = name or st.name
        st.gender = s(raw.get("性别"))
        st.phone = phone
        classes = split_classes(raw.get("所在班级"))
        st.phone_identity = s(raw.get("手机号身份"))
        st.alt_phone = s(raw.get("备用手机号"))
        st.alt_phone_identity = s(raw.get("备用手机号身份"))
        st.birthday = s(raw.get("出生日期"))
        st.age = s(raw.get("年龄"))
        st.grade = s(raw.get("年级"))
        st.school = s(raw.get("学校"))
        st.address = s(raw.get("住址"))
        st.source = s(raw.get("来源"))
        st.follow_up_person = s(raw.get("跟进人"))
        st.manager = s(raw.get("学管师"))
        st.tags = s(raw.get("标签"))
        st.remark = s(raw.get("备注"))
        st.classes = dumps(classes)
        st.created_by = s(raw.get("学员创建人"))
        st.created_time = s(raw.get("创建时间"))
        st.status = "在读"
        st.extra_json = _extra(raw, STUDENT_COLS)
        st.last_batch_id = batch.id

        db.flush()
        for cls in (classes or [""]):
            _upsert_class_teacher(db, sct_cache, st.id, cls, st.follow_up_person)
        index.add(st)
        seen_ids.add(st.id)
        created += int(is_new)
        updated += int(not is_new)

    # 整表覆盖：本次名单之外的学员标记为「不在最新名单」，但保留其作品与历史
    off_list = 0
    for st in db.query(Student).filter(Student.status == "在读").all():
        if st.id not in seen_ids:
            st.status = "不在最新名单"
            off_list += 1

    db.flush()
    return {
        "students_created": created,
        "students_updated": updated,
        "students_off_list": off_list,
        "rows": int(len(df)),
        "skipped": skipped,
    }


# --------------------------------------------------------------------------
# 4.2 学生报读课程 → CourseAccount（核心）
# --------------------------------------------------------------------------

def _import_courses(db: Session, df: pd.DataFrame, batch: ImportBatch) -> dict:
    prev_batch = (db.query(ImportBatch)
                    .filter(ImportBatch.file_type == "courses", ImportBatch.id != batch.id)
                    .order_by(ImportBatch.imported_at.desc(), ImportBatch.id.desc())
                    .first())
    # 偏差报告需要「上期估算剩余」，必须在替换旧账户之前算
    prev_snapshot = _snapshot_previous(db, prev_batch)

    index = StudentIndex(db)
    created_students = 0
    unmatched: list[dict] = []
    accounts: list[CourseAccount] = []
    class_courses: dict[tuple[str, str], int] = {}
    sct_cache: dict = {}
    pending_teachers: list[tuple[int, str, str]] = []

    for i, raw in enumerate(df.to_dict("records")):
        excel_row = i + 2
        name = s(raw.get("学员姓名"))
        student_no = s(raw.get("学号"))
        phone = s(raw.get("手机号"))
        course_name = s(raw.get("课程名称"))
        class_name = s(raw.get("所在班级"))

        if not course_name:
            unmatched.append({"row": excel_row, "student": name, "reason": "缺少课程名称"})
            continue

        st = index.find(student_no, name, phone)
        if st is None:
            if not name and not student_no:
                unmatched.append({"row": excel_row, "student": "", "reason": "缺少学员姓名与学号，无法匹配"})
                continue
            # 报读课程表里出现但学员名单没有 → 按本表字段建档，并记入报告
            st = Student(
                student_no=student_no, name=name, phone=phone,
                phone_identity=s(raw.get("手机号身份")),
                gender=s(raw.get("性别")), grade=s(raw.get("年级")),
                school=s(raw.get("学校")), address=s(raw.get("住址")),
                source=s(raw.get("来源")), birthday=s(raw.get("出生日期")),
                age=s(raw.get("年龄")), tags=s(raw.get("标签")),
                remark=s(raw.get("备注")), follow_up_person=s(raw.get("跟进人")),
                manager=s(raw.get("学管师")), created_by=s(raw.get("学员创建人")),
                classes=dumps(split_classes(class_name)), status="在读",
                last_batch_id=batch.id,
            )
            db.add(st)
            db.flush()
            index.add(st)
            created_students += 1
            unmatched.append({
                "row": excel_row, "student": name or student_no,
                "reason": "学员名单中不存在，已按报读课程表自动建档",
                "level": "info",
            })

        acc = CourseAccount(
            student_id=st.id,
            student_no=st.student_no,
            student_name=st.name,
            course_name=course_name,
            course_type=s(raw.get("课程类型")),
            class_name=class_name,
            purchased=parse_lessons(raw.get("购买数量")),
            gifted=parse_lessons(raw.get("赠送数量")),
            consumed=parse_lessons(raw.get("消耗数量")),
            refunded=parse_lessons(raw.get("退转数量")),
            remaining_imported=parse_lessons(raw.get("剩余数量")),
            over_used=parse_lessons(raw.get("超上数量")),
            consumed_amount=parse_number(raw.get("课消金额")),
            remaining_amount=parse_number(raw.get("剩余课消金额")),
            absent_count=parse_lessons(raw.get("缺课次数")),
            follow_up_person=s(raw.get("跟进人")),
            manager=s(raw.get("学管师")),
            expire_date=parse_date(raw.get("到期时间")),
            suspend_time=s(raw.get("停课时间")),
            resume_time=s(raw.get("复课时间")),
            suspend_remark=s(raw.get("停课备注")),
            extra_json=_extra(raw, COURSE_CORE_COLS),
            import_batch_id=batch.id,
        )
        accounts.append(acc)

        row_teacher = s(raw.get("跟进人"))
        row_classes = split_classes(class_name)
        for cls in row_classes:
            class_courses[(cls, course_name)] = class_courses.get((cls, course_name), 0) + 1
        for cls in (row_classes or [""]):
            pending_teachers.append((st.id, cls, row_teacher))

    # 整表覆盖：删掉旧批次账户，写入本批
    db.query(CourseAccount).filter(CourseAccount.import_batch_id != batch.id).delete(
        synchronize_session=False)
    for acc in accounts:
        db.add(acc)

    # 跟进人合并（在账户重建之后写，保证学员 id 已就绪）
    for student_id, cls, teacher in pending_teachers:
        _upsert_class_teacher(db, sct_cache, student_id, cls, teacher)

    # 班级 → 课程 映射同步重建
    db.query(ClassCourseMap).delete(synchronize_session=False)
    for (cls, course), hits in class_courses.items():
        db.add(ClassCourseMap(class_name=cls, course_name=course, hits=hits,
                              import_batch_id=batch.id))
    db.flush()

    deviation = _deviation_report(db, prev_snapshot, accounts, prev_batch)

    return {
        "rows": int(len(df)),
        "accounts_imported": len(accounts),
        "students_created": created_students,
        "students_matched": len({a.student_id for a in accounts}),
        "class_course_pairs": len(class_courses),
        "unmatched": unmatched,
        "deviation": deviation,
    }


def _snapshot_previous(db: Session, prev_batch: ImportBatch | None) -> list[dict]:
    """上期各账户的估算剩余（导入新批次前拍快照）。"""
    if prev_batch is None:
        return []
    accounts = db.query(CourseAccount).all()
    if not accounts:
        return []
    used_map = used_lessons_map(db, None, prev_batch.imported_at)
    snapshot = []
    for acc in accounts:
        bal = account_balance(acc, used_map, "estimated", prev_batch)
        snapshot.append({
            "student_id": acc.student_id,
            "student_name": acc.student_name,
            "student_no": acc.student_no,
            "course_name": acc.course_name,
            "prev_imported": bal["imported"],
            "prev_estimated": bal["estimated"],
            "used_lessons": bal["used_lessons"],
        })
    return snapshot


def _deviation_report(db: Session, prev_snapshot: list[dict],
                      accounts: list[CourseAccount], prev_batch: ImportBatch | None) -> dict:
    """§6.3 偏差报告：上期估算剩余 vs 本期导入剩余，差值 ≠ 0 的列表。不做自动修正。"""
    if not prev_snapshot:
        return {"available": False, "reason": "首次导入报读课程，无上期数据可对比", "items": []}

    prev_by_key = {(p["student_id"], p["course_name"]): p for p in prev_snapshot}
    items = []
    for acc in accounts:
        prev = prev_by_key.get((acc.student_id, acc.course_name))
        if not prev:
            continue
        actual = int(acc.remaining_imported or 0)
        estimated = int(prev["prev_estimated"])
        diff = estimated - actual
        if diff != 0:
            items.append({
                "student_no": acc.student_no,
                "student_name": acc.student_name,
                "course_name": acc.course_name,
                "estimated": estimated,
                "actual": actual,
                "diff": diff,
            })
    items.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return {
        "available": True,
        "prev_batch_id": prev_batch.id if prev_batch else None,
        "prev_imported_at": prev_batch.imported_at.strftime("%Y-%m-%d %H:%M") if prev_batch else "",
        "compared": len(prev_by_key),
        "count": len(items),
        "items": items,
    }


# --------------------------------------------------------------------------
# 4.3 订单导出 → Order（只读）
# --------------------------------------------------------------------------

def _import_orders(db: Session, df: pd.DataFrame, batch: ImportBatch) -> dict:
    db.query(Order).delete(synchronize_session=False)
    count = 0
    for raw in df.to_dict("records"):
        db.add(Order(
            order_no=s(raw.get("订单号")),
            serial_no=s(raw.get("流水号（支付/退款）")),
            student_name=s(raw.get("学生姓名")),
            phone=s(raw.get("手机号")),
            order_type=s(raw.get("订单类型")),
            purchase_item=s(raw.get("购买项目")),
            due_amount=parse_number(raw.get("应收/应退")),
            paid_amount=parse_number(raw.get("实收/实退")),
            owed_amount=parse_number(raw.get("欠费金额")),
            order_source=s(raw.get("订单来源")),
            performance_owner=s(raw.get("业绩归属人")),
            operator=s(raw.get("经办人")),
            created_time=parse_datetime(raw.get("创建时间")),
            handled_time=s(raw.get("经办时间")),
            last_push_time=s(raw.get("上次推送时间")),
            last_pay_time=s(raw.get("最近支付时间")),
            prepay_status=s(raw.get("先学后付订单状态")),
            order_status=s(raw.get("订单状态")),
            remark=s(raw.get("备注")),
            message=s(raw.get("留言")),
            student_creator=s(raw.get("学生创建人")),
            extra_json=_extra(raw, ORDER_COLS),
            import_batch_id=batch.id,
        ))
        count += 1
    db.flush()
    return {"rows": int(len(df)), "orders_imported": count, "skipped": []}


# --------------------------------------------------------------------------
# 4.4 收支明细 → Transaction（只读）
# --------------------------------------------------------------------------

def _import_transactions(db: Session, df: pd.DataFrame, batch: ImportBatch) -> dict:
    db.query(Transaction).delete(synchronize_session=False)
    count = 0
    for raw in df.to_dict("records"):
        db.add(Transaction(
            created_time=parse_datetime(raw.get("创建时间")),
            item=s(raw.get("收支项目")),
            io_type=s(raw.get("收支类型")),
            status=s(raw.get("状态")),
            amount=parse_number(raw.get("收支金额")),
            pay_method=s(raw.get("支付方式")),
            account=s(raw.get("收支账户")),
            handled_date=s(raw.get("经办日期")),
            operator=s(raw.get("经办人")),
            related_order_no=s(raw.get("关联订单号")),
            payer=s(raw.get("收付款人")),
            pay_serial=s(raw.get("支付流水号")),
            fail_reason=s(raw.get("交易失败原因")),
            remark=s(raw.get("备注")),
            campus=s(raw.get("校区名称")),
            extra_json=_extra(raw, TXN_COLS),
            import_batch_id=batch.id,
        ))
        count += 1
    db.flush()
    return {"rows": int(len(df)), "transactions_imported": count, "skipped": []}


def data_asof(db: Session) -> dict:
    """全站顶栏：学员/课时数据截至时间。"""
    batch = latest_course_batch(db)
    students_batch = (db.query(ImportBatch)
                        .filter(ImportBatch.file_type == "students")
                        .order_by(ImportBatch.imported_at.desc())
                        .first())
    return {
        "courses_asof": batch.imported_at.strftime("%Y-%m-%d %H:%M") if batch else None,
        "students_asof": students_batch.imported_at.strftime("%Y-%m-%d %H:%M") if students_batch else None,
    }
