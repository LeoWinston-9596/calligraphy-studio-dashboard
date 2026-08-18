"""Excel 导入：拖拽上传 → 预览前 5 行 → 确认 → 整表覆盖式更新。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import UPLOAD_TMP_DIR
from ..db import get_db
from ..importer import FILE_TYPES, ImportError_, preview, run_import
from ..models import ImportBatch, User
from ..security import current_user
from ..utils import loads, safe_name

router = APIRouter(prefix="/api/imports", tags=["imports"])

ALLOWED_SUFFIX = (".xls", ".xlsx")


@router.post("/preview")
async def preview_file(file: UploadFile = File(...), _: User = Depends(current_user)):
    name = file.filename or "upload.xls"
    if not name.lower().endswith(ALLOWED_SUFFIX):
        raise HTTPException(status_code=400, detail="只支持 .xls / .xlsx 文件")
    token = uuid.uuid4().hex
    tmp = UPLOAD_TMP_DIR / f"{token}_{safe_name(name)}"
    tmp.write_bytes(await file.read())
    try:
        result = preview(tmp, name)
    except ImportError_ as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"文件解析失败：{e}")
    result["token"] = token
    result["filename"] = name
    return result


@router.post("/confirm")
def confirm(token: str = Body(...), filename: str = Body(...), file_type: str = Body(None),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    # 不用 glob：文件名可能含 [ ] 等通配符字符
    prefix = f"{token}_"
    matches = [p for p in UPLOAD_TMP_DIR.iterdir() if p.is_file() and p.name.startswith(prefix)]
    if not matches:
        raise HTTPException(status_code=400, detail="上传文件已过期，请重新上传")
    tmp = matches[0]
    try:
        report = run_import(db, tmp, filename, user, file_type)
    except ImportError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"导入失败：{e}")
    finally:
        tmp.unlink(missing_ok=True)
    return report


@router.get("/batches")
def batches(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = (db.query(ImportBatch)
              .order_by(ImportBatch.imported_at.desc(), ImportBatch.id.desc())
              .limit(100).all())
    return [{
        "id": b.id,
        "file_type": b.file_type,
        "file_type_label": FILE_TYPES.get(b.file_type, b.file_type),
        "filename": b.filename,
        "imported_by": b.imported_by_name,
        "imported_at": b.imported_at.strftime("%Y-%m-%d %H:%M:%S") if b.imported_at else "",
        "row_count": b.row_count,
    } for b in rows]


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = db.get(ImportBatch, batch_id)
    if not b:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return {
        "id": b.id,
        "file_type": b.file_type,
        "file_type_label": FILE_TYPES.get(b.file_type, b.file_type),
        "filename": b.filename,
        "imported_by": b.imported_by_name,
        "imported_at": b.imported_at.strftime("%Y-%m-%d %H:%M:%S") if b.imported_at else "",
        "row_count": b.row_count,
        "summary": loads(b.summary, {}),
    }


@router.get("/deviation")
def latest_deviation(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """最近一次报读课程导入的偏差报告（§6.3）。"""
    b = (db.query(ImportBatch)
           .filter(ImportBatch.file_type == "courses")
           .order_by(ImportBatch.imported_at.desc(), ImportBatch.id.desc())
           .first())
    if not b:
        return {"available": False, "reason": "尚未导入过报读课程表", "items": []}
    summary = loads(b.summary, {}) or {}
    dev = summary.get("deviation") or {"available": False, "reason": "无偏差数据", "items": []}
    dev["batch_id"] = b.id
    dev["imported_at"] = b.imported_at.strftime("%Y-%m-%d %H:%M") if b.imported_at else ""
    return dev
