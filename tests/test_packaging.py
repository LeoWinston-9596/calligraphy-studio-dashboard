"""打包相关自测：验证冻结后的路径解析不会丢数据。

    python tests/test_packaging.py

打包最容易翻车的地方是路径：PyInstaller 单文件模式下 sys._MEIPASS 是每次启动
临时解压、退出即销毁的目录。要是数据库落在那里，用户每次重启都会发现数据没了。
这里就是专门盯这件事。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Windows 控制台默认是 GBK 代码页，直接 print 中文会抛 UnicodeEncodeError。
# 这会让脚本在 Windows 上直接崩掉，所以强制把标准输出切成 UTF-8。
if sys.platform == "win32":  # pragma: no cover
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

sys.path.insert(0, str(BASE_DIR))

PASS, FAIL, SKIP = [], [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'✅' if ok else '❌'} {name}" + (f"  —— {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIP.append(name)
    print(f"⏭  {name}  —— {why}")


def reload_config(frozen: bool, executable: str = "", meipass: str = ""):
    """模拟冻结/非冻结环境重新加载 config。"""
    old_frozen = getattr(sys, "frozen", None)
    old_exe = sys.executable
    old_mei = getattr(sys, "_MEIPASS", None)
    try:
        if frozen:
            sys.frozen = True
            sys.executable = executable
            if meipass:
                sys._MEIPASS = meipass
        else:
            if hasattr(sys, "frozen"):
                del sys.frozen
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        import app.config as cfg
        return importlib.reload(cfg)
    finally:
        sys.executable = old_exe
        if old_frozen is None:
            if hasattr(sys, "frozen"):
                del sys.frozen
        else:
            sys.frozen = old_frozen
        if old_mei is None:
            if hasattr(sys, "_MEIPASS"):
                del sys._MEIPASS
        else:
            sys._MEIPASS = old_mei


def main() -> int:
    # ---------------------------------------------- 单文件模式（最危险的情况）
    exe = "/Applications/书画室看板/书画室看板"
    mei = "/var/folders/xx/T/_MEI123456"
    cfg = reload_config(True, exe, mei)

    check("[冻结·单文件] 数据目录在 exe 旁边，不在临时解压目录",
          str(cfg.DATA_DIR).startswith("/Applications/书画室看板")
          and "_MEI" not in str(cfg.DATA_DIR), str(cfg.DATA_DIR))
    check("[冻结·单文件] 数据库不在临时目录（否则重启即丢）",
          "_MEI" not in str(cfg.DB_PATH), str(cfg.DB_PATH))
    check("[冻结·单文件] 备份目录在 exe 旁边",
          "_MEI" not in str(cfg.BACKUP_DIR), str(cfg.BACKUP_DIR))
    check("[冻结·单文件] 前端产物走只读资源目录",
          str(cfg.WEB_DIST).startswith(mei), str(cfg.WEB_DIST))

    # ---------------------------------------------- 目录模式
    cfg = reload_config(True, exe)
    check("[冻结·目录] 资源目录 = exe 目录",
          str(cfg.RESOURCE_DIR) == "/Applications/书画室看板", str(cfg.RESOURCE_DIR))
    check("[冻结·目录] 数据目录 = exe 目录/data",
          str(cfg.DATA_DIR) == "/Applications/书画室看板/data", str(cfg.DATA_DIR))

    # ---------------------------------------------- macOS .app 包
    # 这条只在 macOS 上有意义：config 里的 .app 特判是按 sys.platform 生效的，
    # 在 Linux/Windows 上跑必然不成立，跳过而不是误报失败。
    if sys.platform == "darwin":
        app_exe = "/Applications/书画室看板.app/Contents/MacOS/书画室看板"
        cfg = reload_config(True, app_exe)
        check("[冻结·macOS app] 数据不写进 .app 包内部（包内只读）",
              ".app/Contents" not in str(cfg.DATA_DIR), str(cfg.DATA_DIR))
    else:
        skip("[冻结·macOS app] 数据不写进 .app 包内部", f"仅 macOS 适用（当前 {sys.platform}）")

    # ---------------------------------------------- 环境变量覆盖
    import os
    os.environ["SBS_DATA_DIR"] = "/tmp/custom_sbs_data"
    cfg = reload_config(True, exe)
    check("[冻结] 可用 SBS_DATA_DIR 把数据目录挪走",
          str(cfg.DATA_DIR) == "/tmp/custom_sbs_data", str(cfg.DATA_DIR))
    del os.environ["SBS_DATA_DIR"]

    # ---------------------------------------------- 源码模式不受影响
    cfg = reload_config(False)
    check("[源码] 数据目录仍是项目下的 data",
          cfg.DATA_DIR == BASE_DIR / "data", str(cfg.DATA_DIR))
    check("[源码] 前端产物仍是项目下的 web/dist",
          cfg.WEB_DIST == BASE_DIR / "web" / "dist", str(cfg.WEB_DIST))

    # ---------------------------------------------- 打包配置文件齐全
    for name in ("sbs.spec", "build.py", "installer.iss", "打包.bat"):
        check(f"[配置] {name} 存在", (BASE_DIR / name).is_file())

    spec = (BASE_DIR / "sbs.spec").read_text(encoding="utf-8")
    check("[配置] spec 里带上了前端产物", 'web/dist' in spec)
    check("[配置] spec 里带上了语音模型", 'models/' in spec)
    check("[配置] spec 排除了 torch 等大件", 'torch' in spec and 'excludes' in spec)
    check("[配置] 没开 UPX（会压坏 onnxruntime）", 'upx=False' in spec)

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项" +
          (f"，跳过 {len(SKIP)} 项" if SKIP else ""))
    for n in FAIL:
        print("  -", n)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
