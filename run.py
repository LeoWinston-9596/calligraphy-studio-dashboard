#!/usr/bin/env python3
"""书画室本地看板 —— 一条命令启动（macOS / Windows 通用）。

    python run.py

首次运行会自动创建虚拟环境、装依赖、构建前端，然后同时监听：
    http://0.0.0.0:8000    局域网普通访问
    https://0.0.0.0:8443   手机录音需要的安全上下文（自签证书）
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
REQUIREMENTS = BASE_DIR / "requirements.txt"
WEB_DIR = BASE_DIR / "web"
WEB_DIST = WEB_DIR / "dist"
IS_WINDOWS = os.name == "nt"

# Windows 控制台默认是 GBK 代码页，直接 print 中文会抛 UnicodeEncodeError。
# 这会让脚本在 Windows 上直接崩掉，所以强制把标准输出切成 UTF-8。
if sys.platform == "win32":  # pragma: no cover
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass



def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def in_venv() -> bool:
    """当前解释器是否就是本项目 .venv 里的那个。

    注意：不能比较 sys.executable —— .venv/bin/python 通常是指向系统/conda 解释器的
    软链，resolve() 之后两边会变成同一个路径，导致误判。sys.prefix 才是可靠依据。
    """
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def deps_ready() -> bool:
    try:
        import fastapi, pandas, sqlalchemy, uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


# 国内直连 PyPI 经常超时，失败后自动换清华源重试
PIP_MIRRORS = [
    None,  # 先试默认源
    ("https://pypi.tuna.tsinghua.edu.cn/simple", "pypi.tuna.tsinghua.edu.cn"),
    ("https://mirrors.aliyun.com/pypi/simple/", "mirrors.aliyun.com"),
]


def _pip(python: Path, args: list[str], mirror) -> list[str]:
    cmd = [str(python), "-m", "pip", "install", "--timeout", "30", *args]
    if mirror:
        cmd += ["-i", mirror[0], "--trusted-host", mirror[1]]
    return cmd


def install_deps(python: Path) -> None:
    print("· 正在安装依赖（首次较慢，请耐心等待）…")
    env_index = os.environ.get("SBS_PIP_INDEX", "").strip()
    mirrors = [(env_index, env_index.split("/")[2])] if env_index else PIP_MIRRORS

    last_error = None
    for i, mirror in enumerate(mirrors):
        if mirror:
            print(f"  换用镜像源：{mirror[0]}")
        try:
            subprocess.check_call(_pip(python, ["--upgrade", "pip", "-q"], mirror))
            subprocess.check_call(_pip(python, ["-q", "-r", str(REQUIREMENTS)], mirror))
            return
        except subprocess.CalledProcessError as e:
            last_error = e
            if i < len(mirrors) - 1:
                print("  这个源装不上，换国内镜像重试…")
    print("! 依赖安装失败。可以手动指定镜像源后重试：")
    print("  SBS_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple python run.py")
    if last_error:
        raise last_error


def bootstrap() -> None:
    """装齐依赖，必要时切换到 .venv 的解释器重新执行本脚本。"""
    if in_venv():
        # 已经在 .venv 里却缺依赖（venv 不完整）：就地补装，装完再执行一次。
        if os.environ.get("SBS_BOOTSTRAPPED"):
            print("! 依赖安装后仍无法导入，请手动检查：")
            print(f"  {venv_python()} -m pip install -r {REQUIREMENTS}")
            sys.exit(1)
        install_deps(Path(sys.executable))
    else:
        if not venv_python().exists():
            print("· 正在创建虚拟环境 .venv …")
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
        install_deps(venv_python())

    print("· 依赖安装完成，正在启动 …\n")
    env = {**os.environ, "SBS_BOOTSTRAPPED": "1"}
    cmd = [str(venv_python()), str(BASE_DIR / "run.py"), *sys.argv[1:]]
    if IS_WINDOWS:
        # Windows 上 os.execv 语义不同（会立刻返回），用子进程替代
        sys.exit(subprocess.call(cmd, env=env))
    os.execve(cmd[0], cmd, env)


def npm_command() -> str | None:
    from shutil import which
    for name in (("npm.cmd", "npm") if IS_WINDOWS else ("npm",)):
        if which(name):
            return name
    return None


def build_frontend() -> None:
    """dist 不存在时尝试构建；没装 Node 也不影响后端启动。"""
    if (WEB_DIST / "index.html").exists():
        return
    if not WEB_DIR.exists():
        return
    npm = npm_command()
    if not npm:
        print("! 未检测到 Node.js/npm，跳过前端构建。")
        print("  请安装 Node.js 后执行： cd web && npm install && npm run build")
        return
    print("· 正在构建前端（首次较慢）…")
    # 国内直连 npmjs 很慢，装不上就换淘宝镜像重试
    registries = [None, "https://registry.npmmirror.com"]
    env_registry = os.environ.get("SBS_NPM_REGISTRY", "").strip()
    if env_registry:
        registries = [env_registry]
    try:
        if not (WEB_DIR / "node_modules").exists():
            for i, reg in enumerate(registries):
                cmd = [npm, "install"] + (["--registry", reg] if reg else [])
                if reg:
                    print(f"  换用镜像源：{reg}")
                try:
                    subprocess.check_call(cmd, cwd=str(WEB_DIR), shell=IS_WINDOWS)
                    break
                except subprocess.CalledProcessError:
                    if i == len(registries) - 1:
                        raise
                    print("  这个源装不上，换国内镜像重试…")
        subprocess.check_call([npm, "run", "build"], cwd=str(WEB_DIR), shell=IS_WINDOWS)
        print("· 前端构建完成。\n")
    except subprocess.CalledProcessError as e:
        print(f"! 前端构建失败（{e}），后端仍会启动（web/dist 已随包提供）。")


FROZEN = getattr(sys, "frozen", False)


def already_running(port: int) -> bool:
    """端口被占 = 多半是自己已经在跑了。

    双击运行的程序很容易被点第二下，两个实例抢同一个数据库会直接崩，
    所以这里挡掉，顺手把浏览器打开到已经在跑的那个。
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    if not FROZEN:
        # 源码运行：依赖齐了直接跑，缺了就自举
        if not deps_ready():
            bootstrap()
            return
        build_frontend()
        sys.path.insert(0, str(BASE_DIR))
    # 打包版：依赖和前端都已经在包里，什么都不用准备

    import uvicorn

    from app.config import HTTP_PORT, HTTPS_PORT

    if already_running(HTTP_PORT):
        url = f"http://127.0.0.1:{HTTP_PORT}"
        print("=" * 58)
        print("  书画室看板已经在运行了，不用再启动一次。")
        print(f"  访问地址： {url}")
        print("=" * 58)
        if FROZEN:
            import webbrowser
            webbrowser.open(url)
            input("按回车键关闭本窗口…")
        return

    from app.asr import engine_status
    from app.certs import ensure_cert, local_ips
    from app.config import DATA_DIR
    from app.main import app, init_db

    print("正在启动，首次启动需要十几秒，请稍候…")
    init_db()
    cert = ensure_cert()

    ips = [ip for ip in local_ips() if ip != "127.0.0.1"] or ["127.0.0.1"]
    print("=" * 58)
    print("  书画室本地看板已启动")
    print("=" * 58)
    for ip in ips:
        print(f"  电脑访问   http://{ip}:{HTTP_PORT}")
    if cert:
        for ip in ips:
            print(f"  手机访问   https://{ip}:{HTTPS_PORT}   ← 录音需用这个")
        print(f"  录音准备   https://{ips[0]}:{HTTPS_PORT}/cert/help")
        print("  （手机需装一次证书才能录音；不装则录音自动降级为上传音频文件）")
    else:
        print("  ! 未能生成证书，仅提供 HTTP；录音控件会自动降级为上传音频文件")
    print(f"  初始账号   admin / admin123（首次登录需改密）")
    print(f"  数据目录   {DATA_DIR}")
    print(f"  语音转文字 {'已就绪' if engine_status()['available'] else '未启用'}")
    print("  停止服务   关掉这个窗口，或按 Ctrl + C")
    print("=" * 58)

    if FROZEN:
        # 双击启动的用户不会自己去敲地址
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{HTTP_PORT}")).start()

    async def serve() -> None:
        import asyncio

        servers = [uvicorn.Server(uvicorn.Config(
            app, host="0.0.0.0", port=HTTP_PORT, log_level="warning", access_log=False))]
        if cert:
            servers.append(uvicorn.Server(uvicorn.Config(
                app, host="0.0.0.0", port=HTTPS_PORT, log_level="warning", access_log=False,
                ssl_certfile=cert[0], ssl_keyfile=cert[1])))
        # 只让第一个 server 装信号处理器，避免两个 server 互相抢
        for s in servers[1:]:
            s.install_signal_handlers = lambda: None
        await asyncio.gather(*(s.serve() for s in servers))

    import asyncio
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n! 启动失败：{type(e).__name__}: {e}")
        if FROZEN:
            # 打包版是双击运行的，报错窗口一闪而过就没法排查了
            input("按回车键关闭…")
        raise
    print("\n服务已停止。")


if __name__ == "__main__":
    main()
