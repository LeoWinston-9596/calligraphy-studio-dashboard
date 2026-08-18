"""作品照片 / 语音文件的本地存储：data/media/{学号}/{YYYY-MM}/。"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from .config import MEDIA_DIR
from .utils import safe_name

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp"}
AUDIO_EXTS = {".webm", ".ogg", ".oga", ".mp3", ".m4a", ".mp4", ".wav", ".aac", ".amr", ".opus", ".3gp"}

MAX_IMAGE_SIDE = 1600
JPEG_QUALITY = 85


def _folder(student_key: str, day: date | None = None) -> Path:
    day = day or date.today()
    folder = MEDIA_DIR / safe_name(student_key) / f"{day.year:04d}-{day.month:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def rel_path(path: Path) -> str:
    """存库用的相对路径，统一正斜杠，Windows/macOS 一致。"""
    return path.relative_to(MEDIA_DIR).as_posix()


def abs_path(rel: str) -> Path:
    """相对路径 → 绝对路径，并阻止越界访问。"""
    target = (MEDIA_DIR / rel.replace("\\", "/")).resolve()
    root = MEDIA_DIR.resolve()
    if root not in target.parents and target != root:
        raise ValueError("非法媒体路径")
    return target


def save_image(data: bytes, filename: str, student_key: str, day: date | None = None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    folder = _folder(student_key, day)
    out = folder / f"{uuid.uuid4().hex}{ext}"

    compressed = _compress(data, ext)
    if compressed is not None:
        out = out.with_suffix(".jpg")
        out.write_bytes(compressed)
    else:
        out.write_bytes(data)
    return rel_path(out)


def _compress(data: bytes, ext: str) -> bytes | None:
    """有 Pillow 就压缩到长边 1600px 的 JPEG；没有则原样保存。"""
    try:
        import io

        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_IMAGE_SIDE:
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def save_audio(data: bytes, filename: str, student_key: str, day: date | None = None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in AUDIO_EXTS:
        ext = ".webm"
    folder = _folder(student_key, day)
    out = folder / f"{uuid.uuid4().hex}{ext}"
    out.write_bytes(data)
    return rel_path(out)


def content_type(rel: str) -> str:
    ext = Path(rel).suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".heic": "image/heic", ".heif": "image/heif",
        ".webm": "audio/webm", ".ogg": "audio/ogg", ".oga": "audio/ogg",
        ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
        ".wav": "audio/wav", ".aac": "audio/aac", ".amr": "audio/amr",
        ".opus": "audio/opus", ".3gp": "audio/3gpp",
    }.get(ext, "application/octet-stream")


def delete_file(rel: str) -> None:
    try:
        p = abs_path(rel)
        if p.is_file():
            p.unlink()
    except (ValueError, OSError):
        pass
