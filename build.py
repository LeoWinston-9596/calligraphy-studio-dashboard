#!/usr/bin/env python3
"""打包成可分发程序（Windows 出安装包，macOS 出可双击的程序目录）。

    python build.py

做四件事：
  1. 检查前端产物和语音模型在不在（不在就提示怎么补）
  2. 装 PyInstaller
  3. 打包成 dist/书画室看板/（目录模式，启动快）
  4. Windows 上如果装了 Inno Setup，再打成单个安装 exe

打出来的东西**完全离线**：Python 运行时、所有依赖、前端、语音模型全在里面，
目标电脑不需要装 Python，也不需要联网。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WINDOWS = sys.platform == "win32"

# Windows 控制台默认是 GBK 代码页，直接 print 中文会抛 UnicodeEncodeError。
# 这会让脚本在 Windows 上直接崩掉，所以强制把标准输出切成 UTF-8。
if sys.platform == "win32":  # pragma: no cover
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

IS_MAC = sys.platform == "darwin"
APP_NAME = "书画室看板"
DIST = ROOT / "dist" / APP_NAME


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else 0


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def check_prereqs() -> bool:
    ok = True

    step("检查前端产物")
    index = ROOT / "web" / "dist" / "index.html"
    if index.is_file():
        print(f"  ✅ web/dist（{human(dir_size(ROOT / 'web' / 'dist'))}）")
    else:
        print("  ❌ 缺少 web/dist，先构建前端：")
        print("     cd web && npm install && npm run build")
        ok = False

    step("检查语音模型")
    models = ROOT / "data" / "models"
    found = list(models.glob("*/model.int8.onnx")) if models.is_dir() else []
    if found:
        print(f"  ✅ {found[0].parent.name}（{human(dir_size(found[0].parent))}）")
    else:
        print("  ⚠️  没找到语音模型，打出来的程序不带语音转文字。")
        print("     要带上就先执行： python install_asr.py")
        try:
            if input("     没有模型也继续打包？(y/N) ").strip().lower() != "y":
                return False
        except EOFError:
            pass

    step("检查依赖")
    missing = []
    for mod in ("fastapi", "uvicorn", "pandas", "sqlalchemy", "bcrypt", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"  ❌ 缺少 {', '.join(missing)}，先执行： pip install -r requirements.txt")
        ok = False
    else:
        print("  ✅ 核心依赖齐全")
    for mod, label in (("sherpa_onnx", "语音识别"), ("av", "音频解码"), ("pypinyin", "术语纠正")):
        try:
            __import__(mod)
            print(f"  ✅ {label}（{mod}）")
        except ImportError:
            print(f"  ⚠️  缺少 {mod}，打出来的程序没有{label}")
    return ok


def ensure_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        pass
    step("安装 PyInstaller")
    # 国内直连 PyPI 常超时，失败后自动换清华源
    for mirror in (None, ("https://pypi.tuna.tsinghua.edu.cn/simple",
                          "pypi.tuna.tsinghua.edu.cn")):
        cmd = [sys.executable, "-m", "pip", "install", "-q", "--timeout", "30", "pyinstaller"]
        if mirror:
            cmd += ["-i", mirror[0], "--trusted-host", mirror[1]]
            print(f"  换用镜像源：{mirror[0]}")
        try:
            subprocess.check_call(cmd)
            return True
        except subprocess.CalledProcessError as e:
            last = e
    print(f"  ❌ 安装失败：{last}")
    print("     手动装： pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller")
    return False


def build() -> bool:
    step("开始打包（首次较慢，5-15 分钟）")
    for d in (ROOT / "build", ROOT / "dist"):
        shutil.rmtree(d, ignore_errors=True)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "sbs.spec"],
            cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 打包失败：{e}")
        return False
    if not DIST.is_dir():
        print(f"  ❌ 没有生成 {DIST}")
        return False
    print(f"  ✅ 已生成 {DIST}（{human(dir_size(DIST))}）")
    return True


def write_readme() -> None:
    """给最终用户看的说明，跟程序放一起。"""
    exe = f"{APP_NAME}.exe" if IS_WINDOWS else APP_NAME
    (DIST / "使用说明.txt").write_text(f"""书画室本地看板
================================================

启动：双击「{exe}」

启动后会自动打开浏览器。窗口里会显示局域网地址，
老师用手机连同一个 WiFi，在浏览器里输入那个地址就能用。

初始账号：admin / admin123（首次登录会强制改密）

手机要「按住录音」的话，用窗口里显示的 https 地址打开，
并按 /cert/help 页面的步骤装一次证书。不装也能用，
录音会自动变成上传音频文件。

关闭：直接关掉这个黑色窗口。

--------------------------------------------------
数据存在哪
--------------------------------------------------
程序旁边的 data 文件夹里（数据库、照片、录音）。
备份在 backups 文件夹，每天凌晨 2 点自动备一次。

换电脑：把整个文件夹拷过去就行，数据一起带走。
重装程序前请先把 data 文件夹备份出来。

--------------------------------------------------
本程序全程离线运行，不需要联网。
""", encoding="utf-8")


def build_installer() -> None:
    """Windows：有 Inno Setup 就打成单个安装 exe。"""
    if not IS_WINDOWS:
        return
    step("生成安装包")
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if not iscc:
        for guess in (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                      r"C:\Program Files\Inno Setup 6\ISCC.exe"):
            if Path(guess).is_file():
                iscc = guess
                break
    if not iscc:
        print("  ⚠️  没装 Inno Setup，跳过安装包这一步。")
        print("     程序本身已经能用了：把 dist\\书画室看板 整个文件夹拷给对方即可。")
        print("     想要单文件安装包，装一下 Inno Setup 再重跑本脚本：")
        print("     https://jrsoftware.org/isdl.php")
        return
    try:
        subprocess.check_call([iscc, str(ROOT / "installer.iss")], cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 安装包生成失败：{e}")
        return
    out = list((ROOT / "installer_output").glob("*.exe"))
    if out:
        print(f"  ✅ 安装包：{out[0]}（{human(out[0].stat().st_size)}）")


def main() -> int:
    print(f"打包 {APP_NAME}（{sys.platform}, Python {sys.version.split()[0]}）")
    if not check_prereqs():
        return 1
    if not ensure_pyinstaller():
        return 1
    if not build():
        return 1
    write_readme()
    build_installer()

    step("完成")
    print(f"  程序目录：{DIST}")
    if IS_WINDOWS:
        print(f"  启动文件：{DIST / (APP_NAME + '.exe')}")
        print("  交付方式：把 installer_output 里的安装包发给对方（单个文件，离线可用）")
        print("            没有安装包就把 dist\\书画室看板 整个文件夹打个 zip 发过去")
    else:
        print(f"  启动文件：{DIST / APP_NAME}")
        print("  交付方式：把 dist/书画室看板 整个文件夹打包发过去")
    return 0


if __name__ == "__main__":
    sys.exit(main())
