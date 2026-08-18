# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用目录模式（onedir）而不是单文件模式：语音模型有 228MB，单文件模式每次启动
都要把几百 MB 解压到临时目录，慢到不能用。目录模式启动就是秒开，
最终交给用户的仍然是一个安装包（Windows 用 Inno Setup 打成单个 exe）。

构建： python build.py
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH)

# ---------------------------------------------------------------- 资源文件
datas = []

# 前端产物（必须已经 npm run build 过）
web_dist = ROOT / "web" / "dist"
if web_dist.is_dir():
    datas.append((str(web_dist), "web/dist"))

# 语音模型：只带 int8 那份，fp32 的 937MB 用不上
model_root = ROOT / "data" / "models"
if model_root.is_dir():
    for model_dir in model_root.iterdir():
        if not model_dir.is_dir():
            continue
        for f in model_dir.iterdir():
            if f.is_file() and f.name != "model.onnx":
                datas.append((str(f), f"models/{model_dir.name}"))

# ---------------------------------------------------------------- 原生库
# sherpa-onnx / onnxruntime / PyAV 都带 .so/.dylib/.dll，PyInstaller 认不全，手动收
binaries = []
for pkg in ("sherpa_onnx", "onnxruntime", "av"):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# ---------------------------------------------------------------- 隐式导入
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "xlrd", "openpyxl", "pandas",
    "sqlalchemy.dialects.sqlite",
    "bcrypt", "pypinyin", "PIL", "PIL.Image",
    "email.mime.multipart", "email.mime.text",
]
for pkg in ("sherpa_onnx", "av", "pypinyin"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

# 用不上的大件，砍掉能省不少体积
excludes = [
    "tkinter", "matplotlib", "scipy", "notebook", "IPython", "jupyter",
    "torch", "tensorflow", "sklearn", "pytest", "setuptools._distutils",
]

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="书画室看板",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压 onnxruntime 容易压坏，别开
    console=True,       # 保留控制台：要显示局域网访问地址和手机地址
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="书画室看板",
)
