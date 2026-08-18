#!/usr/bin/env python3
"""安装语音转文字模型（一次性，约 228MB）。

    python install_asr.py                # 自动挑最快的源（国内优先）
    python install_asr.py --source github # 指定源：hf-mirror / modelscope / hf / github
    python install_asr.py --file 模型.tar.bz2   # 完全离线：用别处下好的包安装
    python install_asr.py --list         # 只看有哪些源

国内网络说明：默认第一个源是 hf-mirror.com（HuggingFace 国内镜像），
GitHub Releases 放最后 —— 国内直连 GitHub 大文件基本下不动。
只有这一步需要联网，装完之后转写全程离线。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Windows 控制台默认是 GBK 代码页，直接 print 中文会抛 UnicodeEncodeError。
# 这会让脚本在 Windows 上直接崩掉，所以强制把标准输出切成 UTF-8。
if sys.platform == "win32":  # pragma: no cover
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


from app.asr import MODEL_DIR, MODEL_NAME  # noqa: E402

TARGET = MODEL_DIR / MODEL_NAME

# 只下真正要用的两个文件：int8 模型 + 词表。
# GitHub 上那个整包有 999MB，里面 937MB 的 fp32 模型我们根本不用。
FILES = ["model.int8.onnx", "tokens.txt"]

HF_REPO = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"

SOURCES = {
    "hf-mirror": {
        "label": "HuggingFace 国内镜像（推荐，国内最快）",
        "kind": "files",
        "url": f"https://hf-mirror.com/{HF_REPO}/resolve/main/{{file}}",
    },
    "modelscope": {
        "label": "魔搭 ModelScope（阿里，国内可用）",
        "kind": "files",
        "url": "https://modelscope.cn/models/xiaowangge/sherpa-onnx-sense-voice-small"
               "/resolve/master/{file}",
    },
    "hf": {
        "label": "HuggingFace 官方（国内多半连不上）",
        "kind": "files",
        "url": f"https://huggingface.co/{HF_REPO}/resolve/main/{{file}}",
    },
    "github": {
        "label": "GitHub Releases 整包 999MB（国内极慢，最后备选）",
        "kind": "tarball",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
               f"{MODEL_NAME}.tar.bz2",
    },
}
ORDER = ["hf-mirror", "modelscope", "hf", "github"]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class Progress:
    """下载进度。

    输出被重定向到文件时（比如 打包.bat 里）不能用 \\r 刷同一行 ——
    那样会把几万行进度全写进日志。非终端环境改成每 10% 打一行。
    """

    def __init__(self, label: str):
        self.label = label
        self.t0 = time.time()
        self.tty = sys.stdout.isatty()
        self.last_step = -1

    def __call__(self, block_num, block_size, total):
        done = block_num * block_size
        elapsed = max(time.time() - self.t0, 0.001)
        speed = done / elapsed
        if not (total and total > 0):
            if self.tty:
                print(f"\r  已下载 {human(done)}  {human(speed)}/s   ", end="", flush=True)
            return
        done = min(done, total)
        pct = done * 100 / total
        if self.tty:
            bar = "█" * int(pct / 2.5) + "░" * (40 - int(pct / 2.5))
            print(f"\r  {bar} {pct:5.1f}%  {human(done)}/{human(total)}  "
                  f"{human(speed)}/s   ", end="", flush=True)
        else:
            step = int(pct // 10)
            if step > self.last_step:
                self.last_step = step
                print(f"  {pct:5.1f}%  {human(done)}/{human(total)}  {human(speed)}/s",
                      flush=True)


def probe(url: str, timeout: int = 8) -> bool:
    """快速探测源是否可达，避免在死源上干等几分钟。"""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def download_files(name: str, spec: dict, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        url = spec["url"].format(file=f)
        out = dest / f
        if out.is_file() and out.stat().st_size > 0:
            print(f"  {f} 已存在，跳过")
            continue
        print(f"  正在下载 {f}")
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp, reporthook=Progress(f))
            tmp.replace(out)
            print()
        except Exception as e:
            print(f"\n  ! {f} 下载失败：{e}")
            tmp.unlink(missing_ok=True)
            return False
    return True


def download_tarball(name: str, spec: dict, dest: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.tar.bz2"
        print("  正在下载整包（999MB，慢）")
        try:
            urllib.request.urlretrieve(spec["url"], archive, reporthook=Progress("tarball"))
            print()
        except Exception as e:
            print(f"\n  ! 下载失败：{e}")
            return False
        return extract_tarball(archive)


def extract_tarball(archive: Path) -> bool:
    print("  正在解压…")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:*") as tar:
            try:
                tar.extractall(MODEL_DIR, filter="data")
            except TypeError:      # Python < 3.12
                tar.extractall(MODEL_DIR)
    except Exception as e:
        print(f"  ! 解压失败：{e}")
        return False
    # 整包里带了用不到的大文件，删掉省空间
    if TARGET.is_dir():
        for f in list(TARGET.iterdir()):
            if f.is_file() and f.name not in FILES + ["LICENSE", "README.md"]:
                f.unlink(missing_ok=True)
            elif f.is_dir():
                shutil.rmtree(f, ignore_errors=True)
    return True


def installed() -> bool:
    return (TARGET / "model.int8.onnx").is_file() and (TARGET / "tokens.txt").is_file()


def report_installed() -> None:
    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"✅ 语音模型已安装：{TARGET}（{human(size)}）")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--source", choices=list(SOURCES), help="指定下载源")
    ap.add_argument("--file", help="用本地已下好的 .tar.bz2 安装（完全离线）")
    ap.add_argument("--list", action="store_true", help="列出所有可选源")
    ap.add_argument("--force", action="store_true", help="已安装也重新装")
    args = ap.parse_args()

    if args.list:
        print("可选下载源：")
        for k in ORDER:
            print(f"  {k:<12} {SOURCES[k]['label']}")
        print("\n完全离线安装：先在能上网的机器上下好文件，再")
        print("  python install_asr.py --file 路径/模型.tar.bz2")
        return 0

    if installed() and not args.force:
        report_installed()
        print("   要重装请加 --force，或先删掉上面这个目录。")
        return 0

    for mod, pkg in (("sherpa_onnx", "sherpa-onnx"), ("av", "av"), ("pypinyin", "pypinyin")):
        try:
            __import__(mod)
        except ImportError:
            print(f"! 缺少依赖 {pkg}，请先运行： pip install -r requirements.txt")
            return 1

    # ---- 本地文件安装（完全离线）----
    if args.file:
        src = Path(args.file).expanduser()
        if not src.is_file():
            print(f"! 找不到文件：{src}")
            return 1
        print(f"从本地文件安装：{src}")
        if not extract_tarball(src) or not installed():
            print("! 安装失败，请确认这是 sherpa-onnx 的 SenseVoice 模型包")
            return 1
        report_installed()
        return 0

    # ---- 联网安装 ----
    order = [args.source] if args.source else ORDER
    print("正在挑选可用的下载源…\n")
    for name in order:
        spec = SOURCES[name]
        test_url = (spec["url"].format(file="tokens.txt")
                    if spec["kind"] == "files" else spec["url"])
        print(f"→ {name}：{spec['label']}")
        if not args.source and not probe(test_url):
            print("  连不上，换下一个\n")
            continue

        ok = (download_files(name, spec, TARGET) if spec["kind"] == "files"
              else download_tarball(name, spec, TARGET))
        if ok and installed():
            print()
            report_installed()
            print("   重启服务后，新上传的语音评价会自动转成文字。")
            print("   已有旧录音可在「设置 → 语音转文字」点『全部重新转写』。")
            return 0
        print("  这个源没成功，换下一个\n")

    print("\n! 所有源都失败了。可以这样完全离线安装：")
    print("  1. 在网络好的机器上打开：")
    print(f"     https://hf-mirror.com/{HF_REPO}/tree/main")
    print("  2. 下载 model.int8.onnx 和 tokens.txt")
    print(f"  3. 放进目录：{TARGET}")
    print("  4. 重启服务即可")
    return 1


if __name__ == "__main__":
    sys.exit(main())
