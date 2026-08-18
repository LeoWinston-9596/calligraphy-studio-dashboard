"""全局路径与常量。所有路径用 pathlib，Windows / macOS 通用。

打包成可执行程序后有两个不同的根目录，必须分清楚，否则会丢数据：

  RESOURCE_DIR  只读资源（前端产物、语音模型）。PyInstaller 单文件模式下这是
                每次启动临时解压出来的目录，退出即销毁。
  BASE_DIR      可写数据（数据库、照片、录音、备份）。必须指向 exe 所在的真实
                目录 —— 要是跟着 RESOURCE_DIR 走，用户每次重启都会发现数据没了。
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # 资源：单文件模式在 sys._MEIPASS，目录模式就在 exe 旁边
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # 数据：永远放 exe 所在目录，跟着程序走，卸载/升级不丢
    _exe_dir = Path(sys.executable).resolve().parent
    if sys.platform == "darwin" and ".app/Contents/MacOS" in str(_exe_dir):
        # macOS .app 包内部不可写，放到 app 包旁边
        _exe_dir = Path(str(_exe_dir).split(".app/Contents/MacOS")[0]).parent
    BASE_DIR = _exe_dir
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = BASE_DIR

# 允许用环境变量把数据目录挪走（多用户/网络盘场景）
_override = os.environ.get("SBS_DATA_DIR", "").strip()
DATA_DIR = Path(_override).expanduser() if _override else BASE_DIR / "data"
MEDIA_DIR = DATA_DIR / "media"
CERT_DIR = DATA_DIR / "certs"
UPLOAD_TMP_DIR = DATA_DIR / "uploads_tmp"
BACKUP_DIR = BASE_DIR / "backups"
# 前端产物是只读资源，打包后在 RESOURCE_DIR 里
WEB_DIST = RESOURCE_DIR / "web" / "dist"

DB_PATH = DATA_DIR / "app.db"
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

HTTP_PORT = 8000
HTTPS_PORT = 8443

BACKUP_KEEP = 30
BACKUP_HOUR = 2  # 每日 02:00

SESSION_COOKIE = "sbs_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 天

# 设置项默认值（存 AppSetting 表）
DEFAULT_SETTINGS = {
    "balance_mode": "estimated",   # estimated 估算口径 / imported 导入口径
    "renew_threshold": "3",        # 续费预警：剩余 <= N
    "expire_days": "14",           # 到期预警：<= N 天
    "absent_threshold": "2",       # 缺课关注：缺课次数 >= N
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, CERT_DIR, UPLOAD_TMP_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)
