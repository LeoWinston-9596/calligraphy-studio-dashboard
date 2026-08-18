"""语音转文字自测。

    python tests/test_asr.py

模型没装时会自动跳过需要模型的用例，只跑术语纠正与降级逻辑。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

TMP = Path(tempfile.mkdtemp(prefix="sbs_asr_"))
import app.config as config  # noqa: E402

REAL_MODELS = config.DATA_DIR / "models"          # 复用真实模型目录，避免重复下载
config.DATA_DIR = TMP / "data"
config.MEDIA_DIR = config.DATA_DIR / "media"
config.CERT_DIR = config.DATA_DIR / "certs"
config.UPLOAD_TMP_DIR = config.DATA_DIR / "uploads_tmp"
config.BACKUP_DIR = TMP / "backups"
config.DB_PATH = config.DATA_DIR / "app.db"
config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"
config.ensure_dirs()

import app.asr as asr_mod  # noqa: E402

asr_mod.MODEL_DIR = REAL_MODELS
asr_mod.SENSEVOICE_DIR = REAL_MODELS / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
asr_mod._engine.model_dir = asr_mod.SENSEVOICE_DIR

import app.media as media_mod  # noqa: E402

media_mod.MEDIA_DIR = config.MEDIA_DIR

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, init_db  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'✅' if ok else '❌'} {name}" + (f"  —— {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIP.append(name)
    print(f"⏭  {name}  —— {why}")


def make_webm(path: Path, wav: Path) -> bool:
    """把 wav 转成手机实际产生的 webm/opus。"""
    try:
        import wave

        import av
        import numpy as np
        with wave.open(str(wav)) as f:
            sr, n = f.getframerate(), f.getnframes()
            pcm = np.frombuffer(f.readframes(n), dtype=np.int16)
        out = av.open(str(path), "w", format="webm")
        st = out.add_stream("libopus", rate=48000)
        st.layout = "mono"
        res = av.AudioResampler(format="s16", layout="mono", rate=48000)
        fr = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        fr.sample_rate = sr
        fr.pts = None
        for f2 in res.resample(fr):
            for p in st.encode(f2):
                out.mux(p)
        for p in st.encode(None):
            out.mux(p)
        out.close()
        return True
    except Exception as e:
        print("   （生成 webm 失败：", e, "）")
        return False


def main() -> int:
    init_db()
    client = TestClient(app)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    client.post("/api/auth/change-password", json={"new_password": "asr123456"})

    # ---------------------------------------------- 术语纠正（不需要模型）
    from app.terms import correct_text

    cases = [
        ("这幅画的村法不错藏风起笔要再明显一些", "这幅画的皴法不错藏锋起笔要再明显一些"),
        ("今天的中锋用笔很稳注意提案变化和留白", "今天的中锋用笔很稳注意提按变化和留白"),
    ]
    for raw, want in cases:
        got, fixes = correct_text(raw)
        detail = got + " | " + "、".join(f"{c['from']}→{c['to']}" for c in fixes)
        check(f"[纠正] {raw[:10]}…", got == want, detail)

    ok_text, fixes = correct_text("笔画起收笔到位结构比上次更稳")
    check("[纠正] 本来就对的句子不被误改",
          ok_text == "笔画起收笔到位结构比上次更稳" and not fixes, ok_text)

    got, _ = correct_text("")
    check("[纠正] 空字符串不炸", got == "")

    r = client.post("/api/asr/terms/preview", json={"text": "村法很好"})
    check("[术语] 预览接口可用", r.status_code == 200 and r.json()["output"] == "皴法很好",
          r.text[:120])

    # 加术语 → 立即生效
    client.post("/api/asr/terms", json={"text": "枯笔"})
    r = client.post("/api/asr/terms/preview", json={"text": "这里用了哭笔"})
    check("[术语] 新增术语立即生效", "枯笔" in r.json()["output"], r.json()["output"])

    r = client.post("/api/asr/terms", json={"text": "书"})
    check("[术语] 单字被拒绝（避免误伤）", r.status_code == 400, r.text[:80])

    terms = client.get("/api/asr/terms").json()
    tid = next(t["id"] for t in terms["items"] if t["text"] == "枯笔")
    client.patch(f"/api/asr/terms/{tid}", json={"active": False})
    r = client.post("/api/asr/terms/preview", json={"text": "这里用了哭笔"})
    check("[术语] 停用后不再纠正", "枯笔" not in r.json()["output"], r.json()["output"])

    # ---------------------------------------------- 引擎状态
    st = client.get("/api/asr/status").json()
    check("[状态] 状态接口返回完整字段",
          all(k in st for k in ("available", "model_installed", "pending", "term_count")),
          str(list(st)[:6]))

    if not st["available"]:
        skip("[转写] 端到端转写", "语音模型未安装，跑 python install_asr.py 后再测")
        print("\n" + "=" * 60)
        print(f"通过 {len(PASS)}，失败 {len(FAIL)}，跳过 {len(SKIP)}")
        print("=" * 60)
        return 1 if FAIL else 0

    # ---------------------------------------------- 端到端转写
    wav = None
    for cand in (BASE_DIR / "tests" / "fixtures" / "sample.wav",):
        if cand.exists():
            wav = cand
    if wav is None:
        # 现场用 macOS say 生成一段中文
        import subprocess
        aiff = TMP / "s.aiff"
        wav = TMP / "s.wav"
        try:
            subprocess.check_call(["say", "-v", "Tingting", "-o", str(aiff),
                                   "这幅画的皴法不错，藏锋起笔要再明显一些"],
                                  stderr=subprocess.DEVNULL)
            subprocess.check_call(["afconvert", "-f", "WAVE", "-d", "LEI16@16000",
                                   "-c", "1", str(aiff), str(wav)],
                                  stderr=subprocess.DEVNULL)
        except Exception:
            wav = None

    if wav is None or not Path(wav).exists():
        skip("[转写] 端到端转写", "没有可用的测试音频（非 macOS 且无 fixtures）")
    else:
        webm = TMP / "phone.webm"
        used = webm if make_webm(webm, Path(wav)) else Path(wav)

        sid_resp = client.get("/api/students", params={"page_size": 1}).json()
        if not sid_resp["items"]:
            # 没导入数据就现建一个学员
            from app.db import SessionLocal
            from app.models import Student
            db = SessionLocal()
            db.add(Student(student_no="T001", name="测试学员", classes="[]", status="在读"))
            db.commit()
            db.close()
            sid_resp = client.get("/api/students", params={"page_size": 1}).json()
        sid = sid_resp["items"][0]["id"]

        with used.open("rb") as fh:
            r = client.post("/api/artworks", data={
                "student_id": str(sid), "eval_type": "voice", "lesson_date": "2026-08-04",
            }, files=[("audio", (used.name, fh.read(), "audio/webm"))])
        check("[转写] 上传语音立即返回，不阻塞提交",
              r.status_code == 200 and r.json()["transcript_status"] == "pending",
              r.text[:150])
        aid = r.json()["id"]

        from app.transcribe_worker import transcribe_one
        result = transcribe_one(aid)
        check("[转写] 后台转写成功", result.get("ok"), str(result)[:200])

        art = client.get(f"/api/artworks?student_id={sid}").json()[0]
        check("[转写] webm/opus（手机格式）能正确解码转写",
              art["transcript_status"] == "done" and len(art["transcript"]) > 5,
              art["transcript"])
        check("[转写] 专业术语被自动纠正",
              "皴法" in art["transcript"] and "藏锋" in art["transcript"],
              f"{art['transcript']} | 原始 {art['transcript_raw']}")
        check("[转写] 保留原始输出以便回溯",
              bool(art["transcript_raw"]) and art["transcript_raw"] != art["transcript"],
              art["transcript_raw"])

        # 作品集导出带文字稿
        html = client.get(f"/api/students/{sid}/portfolio").text
        check("[导出] 作品集打印版带上语音文字稿",
              "皴法" in html and "语音转文字" in html)

        # 人工校对
        r = client.patch(f"/api/artworks/{aid}/transcript",
                         json={"text": "这幅画的皴法不错，藏锋起笔要再明显一些，继续保持。"})
        check("[校对] 老师可改文字稿并留痕",
              r.json()["transcript_edited"] and r.json()["edit_badge"] == "已编辑",
              str(r.json()["edit_badge"]))
        logs = client.get(f"/api/artworks/{aid}/logs").json()
        check("[校对] 编辑记录含 old→new",
              logs and logs[0]["changes"][0]["field_label"] == "语音文字稿",
              str(logs[0]["changes"][0]["field_label"]) if logs else "无记录")

        # 校对过的不被覆盖
        r = client.post("/api/asr/requeue", json={"only_failed": False})
        check("[校对] 全量重转会跳过人工校对过的", r.json()["queued"] == 0,
              str(r.json()["queued"]))

        transcribe_one(aid)
        art = client.get(f"/api/artworks?student_id={sid}").json()[0]
        check("[校对] 人工版本不被后台覆盖", "继续保持" in art["transcript"],
              art["transcript"])

        # 换录音 → 重新排队
        with used.open("rb") as fh:
            r = client.patch(f"/api/artworks/{aid}",
                             files=[("audio", (used.name, fh.read(), "audio/webm"))])
        check("[转写] 换了录音后旧文字稿作废并重新排队",
              r.json()["transcript_status"] == "pending", str(r.json()["transcript_status"]))

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)}，失败 {len(FAIL)}，跳过 {len(SKIP)}")
    for n in FAIL:
        print("  -", n)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
