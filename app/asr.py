"""语音转文字（本地离线）。

引擎是可替换的：现在跑 SenseVoice-Small（sherpa-onnx，纯 CPU，不装 PyTorch），
以后换 Fun-ASR-Nano 之类只需要再写一个 _Engine 实现，业务代码不用动。

模型不在仓库里（228MB），首次要单独下载一次；没装模型时整个功能优雅降级——
录音照常上传播放，只是没有文字稿，不影响任何既有功能。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR, RESOURCE_DIR

MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
MODEL_DIR = DATA_DIR / "models"


def _find_model_dir() -> Path:
    """先找用户自己装的，再找打包进程序里的。

    打包版把模型放在只读资源目录；用户如果单独跑过 install_asr.py，
    data/models 里那份优先（方便换模型而不用重新打包）。
    """
    candidates = [
        MODEL_DIR / MODEL_NAME,
        RESOURCE_DIR / "models" / MODEL_NAME,
    ]
    for c in candidates:
        if (c / "model.int8.onnx").is_file():
            return c
    return candidates[0]


SENSEVOICE_DIR = _find_model_dir()
SENSEVOICE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
)

TARGET_SR = 16000
MAX_SECONDS = 600  # 单条最长 10 分钟，超出只转前 10 分钟


@dataclass
class Transcript:
    ok: bool
    text: str = ""
    raw_text: str = ""
    corrections: list = field(default_factory=list)
    engine: str = ""
    audio_seconds: float = 0.0
    elapsed: float = 0.0
    error: str = ""


# --------------------------------------------------------------------------
# 音频解码：手机录的是 webm/opus 或 m4a，sherpa-onnx 只吃 16k 单声道 PCM
# --------------------------------------------------------------------------

def decode_audio(path: Path) -> tuple:
    """返回 (numpy float32 单声道 16k, 时长秒)。用 PyAV，自带 ffmpeg，无需外部二进制。"""
    import av
    import numpy as np

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("文件里没有音频轨")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=TARGET_SR)
        chunks: list = []
        total = 0
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                arr = out.to_ndarray().reshape(-1)
                chunks.append(arr)
                total += arr.size
                if total > TARGET_SR * MAX_SECONDS:
                    break
            if total > TARGET_SR * MAX_SECONDS:
                break
        # flush
        try:
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().reshape(-1))
        except Exception:
            pass

    if not chunks:
        raise ValueError("音频解码后为空")
    import numpy as np
    pcm = np.concatenate(chunks).astype(np.float32) / 32768.0
    return pcm, len(pcm) / TARGET_SR


# --------------------------------------------------------------------------
# 引擎
# --------------------------------------------------------------------------

class _SenseVoice:
    name = "sense-voice-small"

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._rec = None
        self._lock = threading.Lock()

    @property
    def model_file(self) -> Path:
        return self.model_dir / "model.int8.onnx"

    @property
    def tokens_file(self) -> Path:
        return self.model_dir / "tokens.txt"

    def available(self) -> bool:
        return self.model_file.is_file() and self.tokens_file.is_file()

    def _ensure(self):
        if self._rec is not None:
            return self._rec
        with self._lock:
            if self._rec is None:
                import sherpa_onnx
                self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=str(self.model_file),
                    tokens=str(self.tokens_file),
                    use_itn=True,          # 数字/日期转成阿拉伯数字写法
                    num_threads=2,         # 后台跑，别把机器吃满
                )
        return self._rec

    def transcribe(self, pcm, sample_rate: int = TARGET_SR) -> str:
        rec = self._ensure()
        stream = rec.create_stream()
        stream.accept_waveform(sample_rate, pcm)
        rec.decode_stream(stream)
        return (stream.result.text or "").strip()


_engine = _SenseVoice(SENSEVOICE_DIR)


def engine_status() -> dict:
    """给设置页看的：模型装没装、装在哪、多大。"""
    ok = _engine.available()
    size = 0
    if ok:
        try:
            size = sum(f.stat().st_size for f in _engine.model_dir.rglob("*") if f.is_file())
        except OSError:
            pass
    try:
        import sherpa_onnx  # noqa: F401
        runtime_ok = True
    except ImportError:
        runtime_ok = False
    try:
        import av  # noqa: F401
        decoder_ok = True
    except ImportError:
        decoder_ok = False
    return {
        "available": ok and runtime_ok and decoder_ok,
        "model_installed": ok,
        "runtime_installed": runtime_ok,
        "decoder_installed": decoder_ok,
        "engine": _engine.name,
        "model_dir": str(_engine.model_dir),
        "model_size": size,
        "download_url": SENSEVOICE_URL,
    }


def transcribe_file(path: Path) -> Transcript:
    """转写单个音频文件，并做书画术语纠正。"""
    from .terms import correct_text

    status = engine_status()
    if not status["available"]:
        missing = []
        if not status["runtime_installed"]:
            missing.append("sherpa-onnx 未安装")
        if not status["decoder_installed"]:
            missing.append("av 未安装")
        if not status["model_installed"]:
            missing.append("语音模型未下载")
        return Transcript(ok=False, error="；".join(missing) or "转写不可用")

    t0 = time.time()
    try:
        pcm, seconds = decode_audio(path)
    except Exception as e:
        return Transcript(ok=False, error=f"音频解码失败：{type(e).__name__}: {e}")

    try:
        raw = _engine.transcribe(pcm)
    except Exception as e:
        return Transcript(ok=False, error=f"转写失败：{type(e).__name__}: {e}")

    text, corrections = correct_text(raw)
    return Transcript(
        ok=True, text=text, raw_text=raw, corrections=corrections,
        engine=_engine.name, audio_seconds=round(seconds, 2),
        elapsed=round(time.time() - t0, 2),
    )
