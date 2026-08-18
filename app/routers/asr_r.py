"""语音转文字的状态、模型安装、术语表管理。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..asr import engine_status
from ..db import get_db
from ..models import Artwork, AsrTerm, User
from ..security import current_user
from ..terms import correct_text, extract_from_templates, load_terms, refresh_cache
from ..transcribe_worker import pending_count

router = APIRouter(prefix="/api/asr", tags=["asr"])


@router.get("/status")
def status(db: Session = Depends(get_db), _: User = Depends(current_user)):
    st = engine_status()
    total_voice = (db.query(Artwork)
                     .filter(Artwork.eval_audio_path.isnot(None),
                             Artwork.deleted == False).count())  # noqa: E712
    done = (db.query(Artwork)
              .filter(Artwork.transcript_status == "done",
                      Artwork.deleted == False).count())  # noqa: E712
    failed = (db.query(Artwork)
                .filter(Artwork.transcript_status == "failed",
                        Artwork.deleted == False).count())  # noqa: E712
    return {
        **st,
        "pending": pending_count(),
        "done": done,
        "failed": failed,
        "total_voice": total_voice,
        "term_count": len(load_terms(db)),
    }


@router.post("/requeue")
def requeue(only_failed: bool = Body(True, embed=True),
            db: Session = Depends(get_db), _: User = Depends(current_user)):
    """把语音评价重新排队转写。默认只重试失败的；补了术语表可以全量重跑。"""
    q = db.query(Artwork).filter(Artwork.eval_audio_path.isnot(None),
                                 Artwork.deleted == False)  # noqa: E712
    if only_failed:
        q = q.filter(Artwork.transcript_status == "failed")
    else:
        q = q.filter(Artwork.transcript_edited == False)  # noqa: E712
    n = 0
    for art in q.all():
        art.transcript_status = "pending"
        n += 1
    db.commit()
    return {"ok": True, "queued": n}


# ------------------------------------------------------------------ 术语表

@router.get("/terms")
def list_terms(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.query(AsrTerm).order_by(AsrTerm.active.desc(), AsrTerm.sort,
                                      AsrTerm.id).all()
    return {
        "items": [{"id": t.id, "text": t.text, "source": t.source,
                   "active": bool(t.active)} for t in rows],
        "suggestions": extract_from_templates(db),
    }


@router.post("/terms")
def add_term(text: str = Body(..., embed=True), db: Session = Depends(get_db),
             _: User = Depends(current_user)):
    text = (text or "").strip()
    if len(text) < 2:
        raise HTTPException(status_code=400, detail="术语至少 2 个字（单字容易误伤）")
    if db.query(AsrTerm).filter(AsrTerm.text == text).first():
        raise HTTPException(status_code=400, detail="这个术语已经在表里了")
    t = AsrTerm(text=text, source="手动", active=True,
                sort=db.query(AsrTerm).count())
    db.add(t)
    db.commit()
    refresh_cache(db)
    return {"id": t.id, "text": t.text, "source": t.source, "active": True}


@router.patch("/terms/{term_id}")
def toggle_term(term_id: int, active: bool = Body(..., embed=True),
                db: Session = Depends(get_db), _: User = Depends(current_user)):
    t = db.get(AsrTerm, term_id)
    if not t:
        raise HTTPException(status_code=404, detail="术语不存在")
    t.active = bool(active)
    db.commit()
    refresh_cache(db)
    return {"id": t.id, "text": t.text, "active": bool(t.active)}


@router.delete("/terms/{term_id}")
def delete_term(term_id: int, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    t = db.get(AsrTerm, term_id)
    if not t:
        raise HTTPException(status_code=404, detail="术语不存在")
    db.delete(t)
    db.commit()
    refresh_cache(db)
    return {"ok": True}


@router.post("/terms/preview")
def preview_correction(text: str = Body(..., embed=True),
                       db: Session = Depends(get_db), _: User = Depends(current_user)):
    """试一下某句话会被纠正成什么，方便教务调术语表。"""
    refresh_cache(db)
    fixed, fixes = correct_text(text or "")
    return {"input": text, "output": fixed, "corrections": fixes}
