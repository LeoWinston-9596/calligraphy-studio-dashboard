"""后台转写队列。

转写放后台跑，老师点提交立刻返回 —— 验收标准里"全程 ≤ 60 秒"不能因为这个功能变慢。
worker 从库里捞 pending 的记录，一条条转，转完写回。进程重启后没转完的会被重新捞起来，
所以不需要额外的队列中间件。
"""
from __future__ import annotations

import asyncio

from .asr import engine_status, transcribe_file
from .db import session_scope
from .media import abs_path
from .models import Artwork
from .utils import dumps

POLL_SECONDS = 5
IDLE_SECONDS = 30


def pending_count() -> int:
    with session_scope() as db:
        return (db.query(Artwork)
                  .filter(Artwork.transcript_status == "pending").count())


def mark_pending(db, artwork: Artwork) -> None:
    """有语音且没人工改过 → 排队等转写。"""
    if artwork.eval_audio_path and not artwork.transcript_edited:
        artwork.transcript_status = "pending"


def transcribe_one(artwork_id: int) -> dict:
    """同步转写一条。给 worker 和「手动重转」接口共用。"""
    with session_scope() as db:
        art = db.get(Artwork, artwork_id)
        if art is None or not art.eval_audio_path:
            return {"ok": False, "error": "没有语音文件"}
        rel = art.eval_audio_path

    try:
        path = abs_path(rel)
    except ValueError:
        path = None
    if path is None or not path.is_file():
        with session_scope() as db:
            art = db.get(Artwork, artwork_id)
            if art:
                art.transcript_status = "failed"
                art.transcript_error = "音频文件不存在"
        return {"ok": False, "error": "音频文件不存在"}

    result = transcribe_file(path)

    with session_scope() as db:
        art = db.get(Artwork, artwork_id)
        if art is None:
            return {"ok": False, "error": "记录已删除"}
        if art.transcript_edited:
            # 转写期间老师手动改过，别覆盖人写的
            art.transcript_status = "done"
            return {"ok": True, "skipped": "已被人工编辑，保留人工版本"}
        if result.ok:
            art.transcript = result.text
            art.transcript_raw = result.raw_text
            art.transcript_corrections = dumps(result.corrections)
            art.transcript_engine = result.engine
            art.transcript_status = "done"
            art.transcript_error = None
        else:
            art.transcript_status = "failed"
            art.transcript_error = result.error
    return {"ok": result.ok, "text": result.text, "error": result.error,
            "corrections": result.corrections, "elapsed": result.elapsed}


def _next_pending() -> int | None:
    with session_scope() as db:
        art = (db.query(Artwork)
                 .filter(Artwork.transcript_status == "pending",
                         Artwork.deleted == False)  # noqa: E712
                 .order_by(Artwork.id).first())
        return art.id if art else None


async def worker() -> None:
    """常驻后台任务。模型没装就干脆歇着，别空转刷日志。"""
    while True:
        try:
            if not engine_status()["available"]:
                await asyncio.sleep(IDLE_SECONDS)
                continue
            artwork_id = await asyncio.to_thread(_next_pending)
            if artwork_id is None:
                await asyncio.sleep(POLL_SECONDS)
                continue
            await asyncio.to_thread(transcribe_one, artwork_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 单条失败不能让 worker 整个挂掉
            await asyncio.sleep(POLL_SECONDS)
