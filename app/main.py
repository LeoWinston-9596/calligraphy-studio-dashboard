"""FastAPI 应用入口。零公网依赖：所有静态资源本地打包，无 CDN。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .backup import scheduler
from .config import WEB_DIST, ensure_dirs
from .db import SessionLocal, engine
from .models import Base
from .routers import (
    alerts, artworks, asr_r, auth, cert, imports, records, settings_r, students, users,
)
from .routers.settings_r import seed_templates
from .security import ensure_admin_seed


# 已发布版本新增的列 → 老库自动补上，避免升级后要重建数据库
MIGRATIONS = {
    "users": [
        ("auto_bind_classes", "BOOLEAN DEFAULT 1"),
        ("teacher_name", "VARCHAR(64) DEFAULT ''"),
        ("teacher_names", "TEXT DEFAULT '[]'"),
    ],
    "artworks": [
        ("transcript", "TEXT"),
        ("transcript_raw", "TEXT"),
        ("transcript_status", "VARCHAR(16) DEFAULT 'none'"),
        ("transcript_engine", "VARCHAR(32)"),
        ("transcript_corrections", "TEXT DEFAULT '[]'"),
        ("transcript_edited", "BOOLEAN DEFAULT 0"),
        ("transcript_error", "TEXT"),
    ],
}


def migrate() -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        for table, columns in MIGRATIONS.items():
            exists = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
            ), {"t": table}).first()
            if not exists:
                continue
            have = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in columns:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def backfill(db) -> None:
    """老库升级：把原来的单值跟进人/单身份灌进新结构，避免必须重新导入。

    回填失败绝不能挡住启动 —— 最坏情况用户重新导入一次 Excel 即可恢复，
    但服务起不来就什么都做不了。
    """
    from .models import CourseAccount, Student, StudentClassTeacher, User
    from .utils import dumps, loads_list, s, split_classes

    # 1) 账号身份 单值 → 多值
    for u in db.query(User).all():
        if not loads_list(u.teacher_names) and (u.teacher_name or "").strip():
            u.teacher_names = dumps([u.teacher_name.strip()])

    # 2) (学员, 班级) → 跟进人。只在表为空时做一次，别覆盖已维护的数据
    if db.query(StudentClassTeacher).first() is None:
        pairs: dict[tuple[int, str], str] = {}
        for st in db.query(Student).all():
            person = s(st.follow_up_person)
            for cls in (loads_list(st.classes) or [""]):
                pairs.setdefault((st.id, cls), person)
        for acc in db.query(CourseAccount).all():
            if not acc.student_id:
                continue
            person = s(acc.follow_up_person)
            for cls in (split_classes(acc.class_name) or [""]):
                if person or (acc.student_id, cls) not in pairs:
                    pairs[(acc.student_id, cls)] = person
        for (student_id, cls), person in pairs.items():
            db.add(StudentClassTeacher(
                student_id=student_id, class_name=cls,
                teachers=dumps([person] if person else []),
                import_teacher=person or "", edit_count=0,
            ))
    db.commit()


def init_db() -> None:
    ensure_dirs()
    Base.metadata.create_all(engine)
    migrate()
    db = SessionLocal()
    try:
        ensure_admin_seed(db)
        seed_templates(db)
        from .terms import seed_terms
        seed_terms(db)
        try:
            backfill(db)
        except Exception as e:
            db.rollback()
            print(f"! 跟进人数据回填失败（不影响启动）：{type(e).__name__}: {e}")
            print("  重新导入一次 Excel 即可补齐。")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .transcribe_worker import worker as transcribe_loop
    tasks = [asyncio.create_task(scheduler()),
             asyncio.create_task(transcribe_loop())]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()


app = FastAPI(title="书画室本地看板", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(imports.router)
app.include_router(students.router)
app.include_router(artworks.router)
app.include_router(artworks.media_router)
app.include_router(alerts.router)
app.include_router(records.router)
app.include_router(settings_r.router)
app.include_router(cert.router)
app.include_router(asr_r.router)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.exception_handler(404)
async def spa_fallback(request: Request, exc):
    """前端是单页应用：非 /api 路径一律回 index.html 交给前端路由。"""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "接口不存在"}, status_code=404)
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return PlainTextResponse(
        "前端尚未构建。请在 web/ 目录执行 npm install && npm run build，"
        "或直接运行 python run.py（会自动构建）。",
        status_code=200,
    )


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIST / "index.html")
