"""数据模型（规格书 §3）。

多值字段（班级、图片列表等）以 JSON 文本存 SQLite；导入表里规格书未列举的列
统一原样保留在 extra_json，保证不丢数据。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def now() -> datetime:
    return datetime.now()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    name = Column(String(64), default="")
    role_label = Column(String(16), default="老师")      # 校长/教务/老师
    class_bindings = Column(Text, default="[]")           # JSON list[str]，手动绑定的班级
    # 自动跟随导入表格：按 teacher_names 匹配「跟进人」，新导入的班级自动归属，无需手选
    auto_bind_classes = Column(Boolean, default=True)
    teacher_names = Column(Text, default="[]")            # JSON list[str]，对应表里的老师名
    teacher_name = Column(String(64), default="")         # 旧单值字段，仅供迁移读取
    active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_no = Column(String(32), index=True)           # 学号
    name = Column(String(64), index=True)
    gender = Column(String(8))
    phone = Column(String(32), index=True)
    phone_identity = Column(String(16))
    alt_phone = Column(String(32))
    alt_phone_identity = Column(String(16))
    birthday = Column(String(32))
    age = Column(String(16))
    grade = Column(String(32))
    school = Column(String(64))
    address = Column(String(255))
    source = Column(String(64))
    follow_up_person = Column(String(64), index=True)     # 跟进人
    manager = Column(String(64))                          # 学管师
    tags = Column(String(255))
    remark = Column(Text)
    classes = Column(Text, default="[]")                  # JSON list[str] 所在班级
    status = Column(String(16), default="在读")
    created_by = Column(String(64))                       # 学员创建人（导入字段）
    created_time = Column(String(32))                     # 创建时间（导入字段，原样字符串）
    extra_json = Column(Text, default="{}")               # 其余导入字段原样保留
    edit_count = Column(Integer, default=0)
    last_batch_id = Column(Integer)
    updated_at = Column(DateTime, default=now, onupdate=now)


class CourseAccount(Base):
    """课时账户 —— 核心表，来自「学生报读课程」。"""
    __tablename__ = "course_accounts"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), index=True)
    student_no = Column(String(32), index=True)
    student_name = Column(String(64))
    course_name = Column(String(128), index=True)
    course_type = Column(String(32))
    class_name = Column(String(128), index=True)
    purchased = Column(Integer, default=0)                # 购买数量
    gifted = Column(Integer, default=0)                   # 赠送数量
    consumed = Column(Integer, default=0)                 # 消耗数量
    refunded = Column(Integer, default=0)                 # 退转数量
    remaining_imported = Column(Integer, default=0)       # 剩余数量（导入口径）
    over_used = Column(Integer, default=0)                # 超上数量
    consumed_amount = Column(Float, default=0.0)          # 课消金额
    remaining_amount = Column(Float, default=0.0)         # 剩余课消金额
    absent_count = Column(Integer, default=0)             # 缺课次数
    follow_up_person = Column(String(64))
    manager = Column(String(64))
    expire_date = Column(Date, index=True)                # 到期时间
    suspend_time = Column(String(32))
    resume_time = Column(String(32))
    suspend_remark = Column(Text)
    extra_json = Column(Text, default="{}")
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), index=True)

    student = relationship("Student")


class StudentClassTeacher(Base):
    """(学员, 班级) → 跟进人列表。

    一个学员报多个班时，每个班可能是不同老师带的，所以跟进人必须按班级记。
    这张表**独立于 CourseAccount**：课时账户每次导入都会整表删除重建，
    跟进人挂在那上面会被冲掉，而手工维护的多老师关系必须活过导入。
    """
    __tablename__ = "student_class_teachers"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), index=True)
    class_name = Column(String(128), index=True)
    teachers = Column(Text, default="[]")            # JSON list[str]，生效值（手工可改）
    import_teacher = Column(String(64), default="")  # 上次导入写进来的那个值，用于合并
    edit_count = Column(Integer, default=0)
    updated_by = Column(Integer)
    updated_by_name = Column(String(64))
    updated_at = Column(DateTime, default=now, onupdate=now)


Index("ix_sct_student_class", StudentClassTeacher.student_id,
      StudentClassTeacher.class_name, unique=True)


class ClassCourseMap(Base):
    """所在班级 → 课程名称 映射（导入报读课程时同步建立）。"""
    __tablename__ = "class_course_map"
    id = Column(Integer, primary_key=True)
    class_name = Column(String(128), index=True)
    course_name = Column(String(128))
    hits = Column(Integer, default=0)                     # 出现次数，同班多课程时取最高
    import_batch_id = Column(Integer)


class Order(Base):
    """订单导出（只读展示）。"""
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_no = Column(String(64), index=True)
    serial_no = Column(String(64))
    student_name = Column(String(64), index=True)
    phone = Column(String(32))
    order_type = Column(String(32))
    purchase_item = Column(Text)
    due_amount = Column(Float)
    paid_amount = Column(Float)
    owed_amount = Column(Float)
    order_source = Column(String(32))
    performance_owner = Column(String(64))
    operator = Column(String(64))
    created_time = Column(DateTime, index=True)
    handled_time = Column(String(32))
    last_push_time = Column(String(32))
    last_pay_time = Column(String(32))
    prepay_status = Column(String(32))
    order_status = Column(String(32))
    remark = Column(Text)
    message = Column(Text)
    student_creator = Column(String(64))
    extra_json = Column(Text, default="{}")
    import_batch_id = Column(Integer, index=True)


class Transaction(Base):
    """收支明细（只读展示）。"""
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    created_time = Column(DateTime, index=True)
    item = Column(String(64))
    io_type = Column(String(16), index=True)              # 收入/支出
    status = Column(String(16))
    amount = Column(Float)
    pay_method = Column(String(32))
    account = Column(String(64))
    handled_date = Column(String(32))
    operator = Column(String(64))
    related_order_no = Column(String(64))
    payer = Column(String(64))
    pay_serial = Column(String(64))
    fail_reason = Column(Text)
    remark = Column(Text)
    campus = Column(String(64))
    extra_json = Column(Text, default="{}")
    import_batch_id = Column(Integer, index=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True)
    file_type = Column(String(32), index=True)            # students|courses|orders|transactions
    filename = Column(String(255))
    imported_by = Column(Integer)
    imported_by_name = Column(String(64))
    imported_at = Column(DateTime, default=now, index=True)
    row_count = Column(Integer, default=0)
    summary = Column(Text, default="{}")                  # JSON：导入报告 + 偏差报告


class Artwork(Base):
    __tablename__ = "artworks"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), index=True)
    class_name = Column(String(128), index=True)
    course_name = Column(String(128), index=True)
    lesson_date = Column(Date, index=True)
    photos = Column(Text, default="[]")                   # JSON list[str]，相对 media 路径，≤3
    eval_type = Column(String(8), default="none")         # voice|text|none
    eval_text = Column(Text)
    eval_audio_path = Column(String(255))
    rating = Column(String(16))                           # 优/良/需加强，可空
    # 语音转文字：raw 是模型原始输出，transcript 是纠正后/老师改过的定稿
    transcript = Column(Text)
    transcript_raw = Column(Text)
    transcript_status = Column(String(16), default="none")  # none|pending|done|failed
    transcript_engine = Column(String(32))
    transcript_corrections = Column(Text, default="[]")   # [{from,to,at}]
    transcript_edited = Column(Boolean, default=False)    # 老师改过就不再被自动覆盖
    transcript_error = Column(Text)
    created_by = Column(Integer)
    created_by_name = Column(String(64))
    created_at = Column(DateTime, default=now, index=True)
    edit_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False, index=True)

    student = relationship("Student")


Index("ix_artwork_student_course", Artwork.student_id, Artwork.course_name, Artwork.lesson_date)


class FollowUp(Base):
    __tablename__ = "follow_ups"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), index=True)
    course_account_id = Column(Integer, index=True)
    alert_type = Column(String(16), index=True)           # renew|expire|absent
    status = Column(String(16), default="待跟进")          # 待跟进|已跟进
    note = Column(Text)
    edit_count = Column(Integer, default=0)
    updated_by = Column(Integer)
    updated_by_name = Column(String(64))
    updated_at = Column(DateTime, default=now, onupdate=now)


class EditLog(Base):
    __tablename__ = "edit_logs"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(32), index=True)          # student|artwork|follow_up|eval_template
    entity_id = Column(Integer, index=True)
    editor_id = Column(Integer)
    editor_name = Column(String(64))
    edited_at = Column(DateTime, default=now, index=True)
    action = Column(String(16), default="update")         # update|delete|restore
    changes_json = Column(Text, default="[]")             # [{field, old, new}]


class EvalTemplate(Base):
    __tablename__ = "eval_templates"
    id = Column(Integer, primary_key=True)
    category = Column(String(16), index=True)             # 书法|美术|通用
    text = Column(Text)
    sort = Column(Integer, default=0)
    edit_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


class AsrTerm(Base):
    """书画术语表，用于纠正语音识别的同音错字（提案→提按、村法→皴法）。"""
    __tablename__ = "asr_terms"
    id = Column(Integer, primary_key=True)
    text = Column(String(32), index=True)
    source = Column(String(16), default="手动")           # 内置|手动
    active = Column(Boolean, default=True)
    sort = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=now, index=True)
    path = Column(String(255))
    kind = Column(String(16), default="auto")             # auto|manual
    size_bytes = Column(Integer, default=0)
    ok = Column(Boolean, default=True)
    message = Column(Text)
