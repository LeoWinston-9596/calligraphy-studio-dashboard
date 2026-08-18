"""书画术语纠正。

语音识别把专业术语写成同音的常用词是通病，实测就有：
    提按 → 提案      皴法 → 村法      藏锋 → 藏风
这些错误全是同音，所以不去跟模型的分词器较劲（实测热词那条路在中文罕用字上
根本编码不了），改成在输出之后按拼音比对术语表来纠正。

好处：与模型无关，换任何引擎都能用；纠了什么一目了然，可回溯；术语表教务自己能维护。
"""
from __future__ import annotations

import threading

from sqlalchemy.orm import Session

from .models import AsrTerm
from .utils import dumps

# 只在这些长度上尝试匹配（覆盖绝大多数术语，也避免过度纠正）
_LENGTHS = (4, 3, 2)

_cache: dict[str, list[str]] = {}
_cache_terms: list[str] = []
_lock = threading.Lock()


def _pinyin(text: str) -> str:
    from pypinyin import lazy_pinyin
    return "".join(lazy_pinyin(text))


def build_index(terms: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for t in terms:
        t = (t or "").strip()
        if len(t) < 2:
            continue           # 单字太容易误伤，不参与纠正
        index.setdefault(_pinyin(t), []).append(t)
    return index


def load_terms(db: Session) -> list[str]:
    rows = (db.query(AsrTerm.text)
              .filter(AsrTerm.active == True)  # noqa: E712
              .order_by(AsrTerm.id).all())
    return [r[0] for r in rows if r[0]]


def refresh_cache(db: Session) -> None:
    global _cache, _cache_terms
    terms = load_terms(db)
    with _lock:
        _cache_terms = terms
        _cache = build_index(terms)


def _ensure_cache() -> tuple[dict, list[str]]:
    if _cache:
        return _cache, _cache_terms
    from .db import SessionLocal
    db = SessionLocal()
    try:
        refresh_cache(db)
    except Exception:
        # 术语表读不到（比如库还没初始化）不该让转写整个失败，退化成不纠正
        return {}, []
    finally:
        db.close()
    return _cache, _cache_terms


def correct_text(text: str, index: dict | None = None,
                 terms: list[str] | None = None) -> tuple[str, list[dict]]:
    """把同音写错的术语换回来。返回 (纠正后文本, [{from, to, at}])。"""
    if not text:
        return "", []
    if index is None:
        index, terms = _ensure_cache()
    if not index:
        return text, []
    known = set(terms or [])

    out: list[str] = []
    fixes: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        matched = False
        for length in _LENGTHS:
            if i + length > n:
                continue
            seg = text[i:i + length]
            if not all("一" <= ch <= "鿿" for ch in seg):
                continue                     # 只在纯汉字片段上纠正
            candidates = index.get(_pinyin(seg))
            if not candidates:
                continue
            if seg in known:                 # 本来就写对了，跳过整个词避免被再切分
                out.append(seg)
            else:
                target = candidates[0]
                out.append(target)
                fixes.append({"from": seg, "to": target, "at": i})
            i += length
            matched = True
            break
        if not matched:
            out.append(text[i])
            i += 1
    return "".join(out), fixes


# --------------------------------------------------------------------------
# 术语表初始化：从评语模板库里抽，老师写过的词天然就是高频术语
# --------------------------------------------------------------------------

SEED_TERMS = [
    # 书法
    "中锋", "侧锋", "藏锋", "露锋", "逆锋", "回锋", "提按", "顿笔", "起笔", "收笔",
    "起收笔", "运笔", "行笔", "笔画", "结构", "章法", "布局", "留白", "中轴线",
    "临帖", "字形", "重心", "横竖", "撇捺", "间架", "笔锋", "力度", "顿挫",
    # 美术
    "皴法", "飞白", "构图", "线条", "造型", "明暗", "层次", "配色", "色彩", "冷暖",
    "透视", "光影", "主体", "背景", "细节", "刻画", "上色", "调色", "笔触", "轮廓",
    # 课堂
    "坐姿", "握笔", "作业", "进步", "认真", "专注", "示范", "练习",
]


def seed_terms(db: Session) -> None:
    if db.query(AsrTerm).count() > 0:
        return
    for i, text in enumerate(SEED_TERMS):
        db.add(AsrTerm(text=text, source="内置", active=True, sort=i))
    db.commit()
    refresh_cache(db)


def extract_from_templates(db: Session) -> list[str]:
    """从评语模板库里挑出已在术语表中的词，用来提示教务哪些词值得加。

    只做候选提示，不自动写入 —— 自动加词容易把常用词也纳入纠正范围，反而误伤。
    """
    from .models import EvalTemplate
    existing = {t for t in load_terms(db)}
    texts = [t[0] for t in db.query(EvalTemplate.text).filter(
        EvalTemplate.deleted == False).all() if t[0]]  # noqa: E712
    found: dict[str, int] = {}
    for text in texts:
        for term in SEED_TERMS:
            if term in text and term not in existing:
                found[term] = found.get(term, 0) + 1
    return [k for k, _ in sorted(found.items(), key=lambda x: -x[1])]
