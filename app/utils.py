"""通用解析/序列化小工具。"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any, Iterable

_LESSON_RE = re.compile(r"-?\d+(?:\.\d+)?")


def is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() in ("", "-", "--", "无", "nan", "NaN", "None"):
        return True
    return False


def s(v: Any, default: str = "") -> str:
    """转干净字符串。"""
    if is_blank(v):
        return default
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v.strftime("%Y-%m-%d")
    return str(v).strip()


def parse_lessons(v: Any) -> int:
    """`"15课时"` → 15；`"0课时"` → 0；空 → 0。"""
    if is_blank(v):
        return 0
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, float):
        return int(round(v))
    m = _LESSON_RE.search(str(v))
    if not m:
        return 0
    return int(round(float(m.group())))


def parse_number(v: Any) -> float:
    if is_blank(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    m = _LESSON_RE.search(str(v).replace(",", ""))
    return float(m.group()) if m else 0.0


_DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y年%m月%d日", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")


def parse_date(v: Any) -> date | None:
    """支持 `2026/08/28`、`2026-08-28`、Excel 原生日期。"""
    if is_blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    txt = str(v).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})", txt)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
               "%Y-%m-%d", "%Y/%m/%d")


def parse_datetime(v: Any) -> datetime | None:
    if is_blank(v):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    txt = str(v).strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            continue
    d = parse_date(txt)
    return datetime(d.year, d.month, d.day) if d else None


def split_classes(v: Any) -> list[str]:
    """`所在班级` 可能是多个班，用中英文逗号/顿号/分号分隔。"""
    txt = s(v)
    if not txt:
        return []
    parts = re.split(r"[,，、;；]", txt)
    return [p.strip() for p in parts if p.strip()]


def normalize_phone(v: Any) -> str:
    txt = s(v)
    return re.sub(r"\D", "", txt)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _json_default(o: Any):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def loads(txt: str | None, default: Any = None):
    if not txt:
        return default if default is not None else None
    try:
        return json.loads(txt)
    except (ValueError, TypeError):
        return default if default is not None else None


def loads_list(txt: str | None) -> list:
    v = loads(txt, [])
    return v if isinstance(v, list) else []


def edit_badge(edit_count: int) -> str:
    """规格书 §7 角标规则。"""
    if not edit_count:
        return ""
    if edit_count == 1:
        return "已编辑"
    if edit_count == 2:
        return "已二次编辑"
    return "已多次编辑"


def date_str(d: date | None) -> str | None:
    return d.isoformat() if d else None


def dt_str(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%d %H:%M:%S") if d else None


def safe_name(txt: str, fallback: str = "unknown") -> str:
    """用于文件夹名：去掉 Windows/macOS 都不允许的字符。"""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(txt)).strip().strip(".")
    return cleaned or fallback


def chunked(seq: Iterable, size: int):
    buf = []
    for item in seq:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
