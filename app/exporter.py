"""导出学员作品集：自包含单页 HTML（照片/语音内嵌，断网也能看，打印即 PDF）。"""
from __future__ import annotations

import base64
from html import escape

from .media import abs_path, content_type
from .models import Artwork, Student
from .utils import loads_list

MAX_EMBED_AUDIO = 8 * 1024 * 1024  # 超过 8MB 的语音不内嵌，避免文件过大


def cn_date(d) -> str:
    """把日期写成「2026年8月18日」。

    不能用 strftime('%Y年%m月%d日')：Windows 的 strftime 走 C 运行时，
    格式串里的中文会按系统代码页编码，直接抛 UnicodeEncodeError，
    导致导出作品集在 Windows 上必然 500。
    """
    if not d:
        return ""
    return f"{d.year}年{d.month}月{d.day}日"


def _data_uri(rel: str) -> str | None:
    try:
        path = abs_path(rel)
        if not path.is_file():
            return None
        raw = path.read_bytes()
    except (ValueError, OSError):
        return None
    return f"data:{content_type(rel)};base64,{base64.b64encode(raw).decode('ascii')}"


def build_portfolio_html(student: Student, artworks: list[Artwork]) -> str:
    title = f"{student.name or ''} 作品集"
    classes = "、".join(loads_list(student.classes)) or "—"
    blocks: list[str] = []

    for art in artworks:
        photos_html = ""
        imgs = []
        for rel in loads_list(art.photos):
            uri = _data_uri(rel)
            if uri:
                imgs.append(f'<img src="{uri}" alt="作品照片">')
        if imgs:
            photos_html = f'<div class="photos">{"".join(imgs)}</div>'

        eval_html = ""
        if art.eval_type == "text" and art.eval_text:
            eval_html = f'<p class="eval-text">{escape(art.eval_text)}</p>'
        elif art.eval_type == "voice" and art.eval_audio_path:
            name = art.eval_audio_path.rsplit("/", 1)[-1]
            uri = _data_uri(art.eval_audio_path)
            # 语音的文字稿要一起带上：打印出来的册子放不了音频，
            # 没有文字稿的话这一条在纸上就是空的
            transcript = ""
            if art.transcript:
                tag = "" if art.transcript_edited else '<span class="asr-tag">语音转文字</span>'
                transcript = f'<p class="eval-text">{escape(art.transcript)}{tag}</p>'
            if uri and len(uri) < MAX_EMBED_AUDIO * 1.4:
                eval_html = (
                    f'{transcript}<div class="eval-audio"><audio controls src="{uri}"></audio>'
                    f'<a class="audio-link" href="{uri}" download="{escape(name)}">'
                    f'下载语音评价（{escape(name)}）</a></div>'
                )
            else:
                eval_html = transcript or f'<p class="eval-text">语音评价文件：{escape(name)}</p>'
        elif art.eval_text:
            eval_html = f'<p class="eval-text">{escape(art.eval_text)}</p>'

        rating_html = f'<span class="rating">{escape(art.rating)}</span>' if art.rating else ""
        meta = " · ".join(x for x in [art.course_name or "", art.class_name or ""] if x)
        blocks.append(f"""
    <section class="entry">
      <header>
        <span class="date">{cn_date(art.lesson_date)}</span>
        <span class="meta">{escape(meta)}</span>
        {rating_html}
      </header>
      {photos_html}
      {eval_html}
      <footer>记录人：{escape(art.created_by_name or '')}</footer>
    </section>""")

    body = "".join(blocks) or '<p class="empty">暂无作品记录</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:20px; background:#f6f5f2; color:#2b2b2b;
         font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
         line-height:1.6; }}
  .wrap {{ max-width:820px; margin:0 auto; }}
  h1 {{ font-size:26px; margin:0 0 6px; letter-spacing:2px; }}
  .sub {{ color:#7a746c; font-size:14px; margin-bottom:20px; }}
  .entry {{ background:#fff; border-radius:12px; padding:16px; margin-bottom:16px;
            box-shadow:0 1px 3px rgba(0,0,0,.08); break-inside:avoid; }}
  .entry header {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap;
                   border-bottom:1px solid #eee; padding-bottom:8px; margin-bottom:12px; }}
  .date {{ font-weight:600; font-size:16px; }}
  .meta {{ color:#8a8378; font-size:13px; }}
  .rating {{ margin-left:auto; background:#f3e9d8; color:#8a6d3b; border-radius:99px;
             padding:2px 10px; font-size:13px; }}
  .photos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; }}
  .photos img {{ width:100%; border-radius:8px; display:block; }}
  .eval-text {{ margin:12px 0 0; white-space:pre-wrap; }}
  .asr-tag {{ display:inline-block; margin-left:6px; font-size:11px; color:#a49c90;
              border:1px solid #e5e2dc; border-radius:99px; padding:1px 7px;
              vertical-align:middle; white-space:nowrap; }}
  .eval-audio {{ margin-top:12px; }}
  .eval-audio audio {{ width:100%; }}
  .audio-link {{ display:inline-block; margin-top:6px; font-size:13px; color:#8a6d3b; }}
  .entry footer {{ margin-top:10px; color:#a49c90; font-size:12px; }}
  .empty {{ color:#8a8378; }}
  @media print {{
    body {{ background:#fff; padding:0; }}
    .entry {{ box-shadow:none; border:1px solid #e5e2dc; }}
    .audio-link, audio {{ display:none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{escape(title)}</h1>
  <div class="sub">学号 {escape(student.student_no or '—')} · 班级 {escape(classes)} · 共 {len(artworks)} 条记录</div>
  {body}
</div>
</body>
</html>"""
