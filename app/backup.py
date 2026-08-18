"""备份（规格书 §8）：每日 02:00 增量打包 app.db + media/ 到 backups/YYYY-MM-DD/，保留 30 份。"""
from __future__ import annotations

import asyncio
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .config import BACKUP_DIR, BACKUP_HOUR, BACKUP_KEEP, DB_PATH, MEDIA_DIR
from .db import session_scope
from .models import BackupRecord
from .utils import dumps, loads

MANIFEST = "manifest.json"


def _media_manifest() -> dict[str, list]:
    """记录每个媒体文件的 大小+修改时间，用于判断增量。"""
    out: dict[str, list] = {}
    if not MEDIA_DIR.exists():
        return out
    for p in MEDIA_DIR.rglob("*"):
        if p.is_file():
            stat = p.stat()
            out[p.relative_to(MEDIA_DIR).as_posix()] = [stat.st_size, int(stat.st_mtime)]
    return out


def _last_manifest() -> dict[str, list]:
    dirs = sorted([d for d in BACKUP_DIR.glob("*") if d.is_dir()], reverse=True)
    for d in dirs:
        mf = d / MANIFEST
        if mf.exists():
            data = loads(mf.read_text(encoding="utf-8"), {}) or {}
            return data.get("media", {})
    return {}


def run_backup(kind: str = "auto") -> dict:
    """执行一次备份。数据库整份复制，媒体只打包新增/变更文件。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    day_dir = BACKUP_DIR / datetime.now().strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")

    result = {"ok": True, "path": day_dir.as_posix(), "kind": kind}
    try:
        # 1) 数据库：用 sqlite 在线备份 API，避免 WAL 下拷贝到不一致状态
        db_target = day_dir / f"app-{stamp}.db"
        _backup_sqlite(DB_PATH, db_target)

        # 2) 媒体增量
        current = _media_manifest()
        previous = _last_manifest()
        changed = [rel for rel, meta in current.items() if previous.get(rel) != meta]
        media_zip = day_dir / f"media-{stamp}.zip"
        if changed:
            with zipfile.ZipFile(media_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel in changed:
                    zf.write(MEDIA_DIR / rel, rel)
        else:
            media_zip = None

        (day_dir / MANIFEST).write_text(dumps({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "db": db_target.name,
            "media_zip": media_zip.name if media_zip else None,
            "media_changed": len(changed),
            "media_total": len(current),
            "media": current,
        }), encoding="utf-8")

        size = sum(f.stat().st_size for f in day_dir.glob("*") if f.is_file())
        result.update({"size_bytes": size, "media_changed": len(changed),
                       "media_total": len(current)})
        _prune()
    except Exception as e:  # 备份失败不能影响主服务
        result.update({"ok": False, "message": f"{type(e).__name__}: {e}"})

    with session_scope() as db:
        db.add(BackupRecord(
            path=result["path"], kind=kind, ok=result["ok"],
            size_bytes=result.get("size_bytes", 0), message=result.get("message"),
        ))
    return result


def _backup_sqlite(src: Path, dst: Path) -> None:
    import sqlite3
    if not src.exists():
        return
    source = sqlite3.connect(str(src))
    target = sqlite3.connect(str(dst))
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()


def _prune() -> None:
    dirs = sorted([d for d in BACKUP_DIR.glob("*") if d.is_dir()])
    while len(dirs) > BACKUP_KEEP:
        shutil.rmtree(dirs.pop(0), ignore_errors=True)


def backup_status(db: Session) -> dict:
    last = (db.query(BackupRecord).filter(BackupRecord.ok == True)  # noqa: E712
              .order_by(BackupRecord.created_at.desc()).first())
    last_at = last.created_at if last else None
    stale = True
    if last_at:
        stale = (datetime.now() - last_at) > timedelta(hours=48)
    count = len([d for d in BACKUP_DIR.glob("*") if d.is_dir()]) if BACKUP_DIR.exists() else 0
    return {
        "last_backup_at": last_at.strftime("%Y-%m-%d %H:%M:%S") if last_at else None,
        "last_backup_kind": last.kind if last else None,
        "last_backup_size": last.size_bytes if last else 0,
        "stale": stale,                      # 超过 48 小时 → 全站顶部黄条
        "keep": BACKUP_KEEP,
        "backup_days": count,
        "backup_dir": BACKUP_DIR.as_posix(),
    }


async def scheduler() -> None:
    """每日 02:00 自动备份。"""
    while True:
        now = datetime.now()
        nxt = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep(max(60.0, (nxt - now).total_seconds()))
        try:
            await asyncio.to_thread(run_backup, "auto")
        except Exception:
            pass
