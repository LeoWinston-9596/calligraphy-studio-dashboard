"""作品与评价（规格书 §5.2、§7）。"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import media
from ..balance import course_of_class
from ..db import get_db
from ..editlog import apply_update, file_changes, record_edit
from ..models import Artwork, Student, User
from ..security import current_user
from ..utils import date_str, dt_str, dumps, edit_badge, loads_list, parse_date

router = APIRouter(prefix="/api/artworks", tags=["artworks"])

MAX_PHOTOS = 3
EVAL_TYPES = ("voice", "text", "none")
RATINGS = ("优", "良", "需加强", "")


def artwork_out(a: Artwork, student: Student | None = None) -> dict:
    photos = loads_list(a.photos)
    return {
        "id": a.id,
        "student_id": a.student_id,
        "student_name": student.name if student else (a.student.name if a.student else ""),
        "class_name": a.class_name,
        "course_name": a.course_name,
        "lesson_date": date_str(a.lesson_date),
        "photos": [f"/api/media/{p}" for p in photos],
        "photo_paths": photos,
        "eval_type": a.eval_type,
        "eval_text": a.eval_text or "",
        "eval_audio": f"/api/media/{a.eval_audio_path}" if a.eval_audio_path else None,
        "transcript": a.transcript or "",
        "transcript_raw": a.transcript_raw or "",
        "transcript_status": a.transcript_status or "none",
        "transcript_corrections": loads_list(a.transcript_corrections),
        "transcript_edited": bool(a.transcript_edited),
        "transcript_error": a.transcript_error or "",
        "rating": a.rating or "",
        "created_by": a.created_by_name,
        "created_at": dt_str(a.created_at),
        "edit_count": a.edit_count or 0,
        "edit_badge": edit_badge(a.edit_count or 0),
        "deleted": bool(a.deleted),
    }


def _student_key(st: Student) -> str:
    return st.student_no or f"S{st.id}"


@router.post("")
async def create_artwork(
    student_id: int = Form(...),
    class_name: str = Form(""),
    course_name: str = Form(""),
    lesson_date: str = Form(""),
    eval_type: str = Form("none"),
    eval_text: str = Form(""),
    rating: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    audio: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    st = db.get(Student, student_id)
    if not st:
        raise HTTPException(status_code=404, detail="学员不存在")
    if eval_type not in EVAL_TYPES:
        eval_type = "none"
    if rating not in RATINGS:
        rating = ""

    day = parse_date(lesson_date) or date.today()
    class_name = (class_name or "").strip()
    course_name = (course_name or "").strip() or (course_of_class(db, class_name) or "")

    files = [f for f in (photos or []) if f and f.filename]
    if len(files) > MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"最多上传 {MAX_PHOTOS} 张照片")

    key = _student_key(st)
    saved: list[str] = []
    for f in files:
        data = await f.read()
        if data:
            saved.append(media.save_image(data, f.filename, key, day))

    audio_path = None
    if eval_type == "voice" and audio is not None and audio.filename:
        data = await audio.read()
        if data:
            audio_path = media.save_audio(data, audio.filename, key, day)
    if eval_type == "voice" and not audio_path:
        # 录音没传上来时降级为文字/无评价，避免出现空的语音卡片
        eval_type = "text" if eval_text.strip() else "none"

    art = Artwork(
        student_id=st.id,
        class_name=class_name,
        course_name=course_name,
        lesson_date=day,
        photos=dumps(saved),
        eval_type=eval_type,
        eval_text=eval_text.strip() if eval_type == "text" else (eval_text.strip() or None),
        eval_audio_path=audio_path,
        rating=rating,
        created_by=user.id,
        created_by_name=user.name or user.username,
        created_at=datetime.now(),
        edit_count=0,
        deleted=False,
        # 有语音就排队等后台转写，不阻塞老师提交
        transcript_status="pending" if audio_path else "none",
    )
    db.add(art)
    db.commit()
    return artwork_out(art, st)


@router.get("")
def list_artworks(
    student_id: int | None = Query(None),
    class_name: str = Query(""),
    lesson_date: str = Query(""),
    include_deleted: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    q = db.query(Artwork)
    if not include_deleted:
        q = q.filter(Artwork.deleted == False)  # noqa: E712
    if student_id:
        q = q.filter(Artwork.student_id == student_id)
    if class_name:
        q = q.filter(Artwork.class_name == class_name)
    d = parse_date(lesson_date)
    if d:
        q = q.filter(Artwork.lesson_date == d)
    rows = q.order_by(Artwork.lesson_date.desc(), Artwork.id.desc()).limit(limit).all()
    return [artwork_out(a) for a in rows]


@router.patch("/{artwork_id}")
async def update_artwork(
    artwork_id: int,
    lesson_date: str = Form(None),
    class_name: str = Form(None),
    course_name: str = Form(None),
    eval_type: str = Form(None),
    eval_text: str = Form(None),
    rating: str = Form(None),
    keep_photos: str = Form(None),          # JSON list：保留的照片相对路径
    photos: list[UploadFile] = File(default=[]),
    audio: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    art = db.get(Artwork, artwork_id)
    if not art:
        raise HTTPException(status_code=404, detail="作品不存在")
    st = db.get(Student, art.student_id)

    updates: dict = {}
    if lesson_date is not None:
        d = parse_date(lesson_date)
        if d:
            updates["lesson_date"] = d
    if class_name is not None:
        updates["class_name"] = class_name.strip()
    if course_name is not None:
        updates["course_name"] = course_name.strip()
    elif class_name is not None:
        mapped = course_of_class(db, class_name.strip())
        if mapped:
            updates["course_name"] = mapped
    if rating is not None and rating in RATINGS:
        updates["rating"] = rating
    if eval_text is not None:
        updates["eval_text"] = eval_text.strip()
    if eval_type is not None and eval_type in EVAL_TYPES:
        updates["eval_type"] = eval_type

    # 照片增删
    old_photos = loads_list(art.photos)
    new_photos = old_photos
    if keep_photos is not None or (photos and any(f.filename for f in photos)):
        from ..utils import loads
        keep = loads(keep_photos, None) if keep_photos is not None else old_photos
        keep = [p for p in (keep or []) if p in old_photos]
        added: list[str] = []
        key = _student_key(st) if st else "unknown"
        for f in (photos or []):
            if f and f.filename:
                data = await f.read()
                if data:
                    added.append(media.save_image(data, f.filename, key, art.lesson_date))
        new_photos = keep + added
        if len(new_photos) > MAX_PHOTOS:
            for p in added:
                media.delete_file(p)
            raise HTTPException(status_code=400, detail=f"最多保留 {MAX_PHOTOS} 张照片")

    # 语音替换
    audio_change: list[dict] = []
    if audio is not None and audio.filename:
        data = await audio.read()
        if data:
            key = _student_key(st) if st else "unknown"
            new_audio = media.save_audio(data, audio.filename, key, art.lesson_date)
            audio_change = file_changes(
                "eval_audio_path",
                [art.eval_audio_path] if art.eval_audio_path else [],
                [new_audio],
            )
            old_audio = art.eval_audio_path
            art.eval_audio_path = new_audio
            art.eval_type = "voice"
            # 换了录音，旧文字稿作废，重新排队
            art.transcript_status = "pending"
            art.transcript_edited = False
            art.transcript = None
            art.transcript_raw = None
            if old_audio:
                media.delete_file(old_audio)

    photo_change = file_changes("photos", old_photos, new_photos) if new_photos != old_photos else []
    if photo_change:
        for p in old_photos:
            if p not in new_photos:
                media.delete_file(p)
        art.photos = dumps(new_photos)

    from ..editlog import diff_changes
    field_changes = diff_changes(art, updates)
    for k, v in updates.items():
        setattr(art, k, v)

    all_changes = field_changes + photo_change + audio_change
    record_edit(db, art, "artwork", all_changes, user)
    db.commit()
    return {**artwork_out(art, st), "changed": all_changes}


@router.delete("/{artwork_id}")
def delete_artwork(artwork_id: int, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    """软删除：时间轴不显示，编辑记录可查，估算余额随之回退。"""
    art = db.get(Artwork, artwork_id)
    if not art:
        raise HTTPException(status_code=404, detail="作品不存在")
    if art.deleted:
        return {"ok": True, "already": True}
    art.deleted = True
    record_edit(db, art, "artwork",
                [{"field": "deleted", "field_label": "删除状态", "old": False, "new": True}],
                user, action="delete")
    db.commit()
    return {"ok": True, "edit_count": art.edit_count, "edit_badge": edit_badge(art.edit_count or 0)}


@router.post("/{artwork_id}/restore")
def restore_artwork(artwork_id: int, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    art = db.get(Artwork, artwork_id)
    if not art:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not art.deleted:
        return {"ok": True, "already": True}
    art.deleted = False
    record_edit(db, art, "artwork",
                [{"field": "deleted", "field_label": "删除状态", "old": True, "new": False}],
                user, action="restore")
    db.commit()
    return {"ok": True}


@router.get("/{artwork_id}/logs")
def artwork_logs(artwork_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..editlog import logs_for
    return logs_for(db, "artwork", artwork_id)


# ---------------------------------------------------------------- 语音转文字

@router.post("/{artwork_id}/transcribe")
async def retranscribe(artwork_id: int, db: Session = Depends(get_db),
                       _: User = Depends(current_user)):
    """手动重新转写（比如刚补了术语表，想让这条重跑一遍）。"""
    art = db.get(Artwork, artwork_id)
    if not art:
        raise HTTPException(status_code=404, detail="作品不存在")
    if not art.eval_audio_path:
        raise HTTPException(status_code=400, detail="这条没有语音评价")

    from ..asr import engine_status
    if not engine_status()["available"]:
        raise HTTPException(status_code=400, detail="语音转文字未就绪，请先在设置页安装模型")

    art.transcript_edited = False   # 手动重转 = 放弃人工版本
    db.commit()

    from ..transcribe_worker import transcribe_one
    result = await asyncio.to_thread(transcribe_one, artwork_id)
    db.expire_all()
    art = db.get(Artwork, artwork_id)
    return {**artwork_out(art), "result": result}


@router.patch("/{artwork_id}/transcript")
def edit_transcript(artwork_id: int, text: str = Body(..., embed=True),
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    """老师订正机器转写稿。改过之后后台不会再覆盖它。"""
    art = db.get(Artwork, artwork_id)
    if not art:
        raise HTTPException(status_code=404, detail="作品不存在")

    old = art.transcript or ""
    new = (text or "").strip()
    if old == new:
        return {**artwork_out(art), "changed": []}

    art.transcript = new
    art.transcript_edited = True
    art.transcript_status = "done"
    changes = [{"field": "transcript", "field_label": "语音文字稿",
                "old": old, "new": new}]
    record_edit(db, art, "artwork", changes, user)
    db.commit()
    return {**artwork_out(art), "changed": changes}


# ---------------------------------------------------------------- 媒体文件

media_router = APIRouter(prefix="/api/media", tags=["media"])


@media_router.get("/{rel_path:path}")
def get_media(rel_path: str, _: User = Depends(current_user)):
    try:
        path = media.abs_path(rel_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法路径")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type=media.content_type(rel_path),
                        headers={"Cache-Control": "private, max-age=86400"})
