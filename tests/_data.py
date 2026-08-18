"""测试数据定位。

仓库里不含任何真实导出表（内含学员姓名、家长手机号、住址），所以测试不能
硬编码文件名，也不能硬编码里面的人名。这里按**列名特征**自动识别项目根目录下
放着的导出文件 —— 你把自己的四个 Excel 放进项目根目录，测试就能跑。

Test fixtures are intentionally absent from the repository: the real exports contain
student names, guardian phone numbers and home addresses. Drop your own exports into
the project root and the suites will pick them up by column signature.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

warnings.filterwarnings("ignore")

# Windows 控制台默认是 GBK 代码页，直接 print 中文会抛 UnicodeEncodeError。
# 这会让脚本在 Windows 上直接崩掉，所以强制把标准输出切成 UTF-8。
if sys.platform == "win32":  # pragma: no cover
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


HINT = """
未找到教务导出文件，跳过依赖真实数据的用例。

想跑完整测试，把你自己的四个导出表放到项目根目录：
  · 在读学员名单   *.xls
  · 学生报读课程   *.xls
  · 订单导出       *.xlsx
  · 收支明细       *.xls
文件名随意，系统按列名自动识别。这些文件已被 .gitignore 排除，不会进仓库。

No exported spreadsheets found; data-dependent checks are skipped.
Drop your own exports (any filename) into the project root to run the full suite.
They are git-ignored and will never be committed.
"""


def find_exports() -> dict[str, Path]:
    """{类型: 路径}，类型为 students / courses / orders / transactions。"""
    from app.importer import detect_type, read_excel

    found: dict[str, Path] = {}
    for path in sorted(BASE_DIR.glob("*.xls")) + sorted(BASE_DIR.glob("*.xlsx")):
        if path.name.startswith("~$"):        # Excel 临时文件
            continue
        try:
            ftype = detect_type(read_excel(path), path.name)
        except Exception:
            continue
        found.setdefault(ftype, path)
    return found


def import_all(client, exports: dict[str, Path], only: list[str] | None = None) -> dict:
    """把导出表通过接口导进去，返回 {类型: 导入报告}。"""
    reports = {}
    for ftype, path in exports.items():
        if only and ftype not in only:
            continue
        with path.open("rb") as fh:
            pv = client.post("/api/imports/preview",
                             files={"file": (path.name, fh.read())}).json()
        if "token" not in pv:
            continue
        reports[ftype] = client.post(
            "/api/imports/confirm",
            json={"token": pv["token"], "filename": path.name}).json()
    return reports
