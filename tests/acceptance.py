"""验收自测（规格书 §9）：逐条跑通 1-7。

    python tests/acceptance.py

会使用一个独立的临时数据目录，不影响 data/ 下的真实数据。
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 在导入 app 之前把数据目录指向临时目录
TMP = Path(tempfile.mkdtemp(prefix="sbs_test_"))
import app.config as config  # noqa: E402

config.DATA_DIR = TMP / "data"
config.MEDIA_DIR = config.DATA_DIR / "media"
config.CERT_DIR = config.DATA_DIR / "certs"
config.UPLOAD_TMP_DIR = config.DATA_DIR / "uploads_tmp"
config.BACKUP_DIR = TMP / "backups"
config.DB_PATH = config.DATA_DIR / "app.db"
config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"
config.ensure_dirs()

from _data import HINT, find_exports  # noqa: E402

try:
    from fastapi.testclient import TestClient  # noqa: E402
except RuntimeError as e:  # TestClient 需要 httpx，属于测试专用依赖
    print("缺少测试依赖，请先执行：")
    print("  .venv/bin/pip install -r requirements-dev.txt      # macOS")
    print("  .venv\\Scripts\\pip install -r requirements-dev.txt  # Windows")
    print(f"\n原始错误：{e}")
    sys.exit(2)

import app.media as media_mod  # noqa: E402

media_mod.MEDIA_DIR = config.MEDIA_DIR
import app.backup as backup_mod  # noqa: E402

backup_mod.BACKUP_DIR = config.BACKUP_DIR
backup_mod.DB_PATH = config.DB_PATH
backup_mod.MEDIA_DIR = config.MEDIA_DIR

from app.exporter import cn_date  # noqa: E402
from app.main import app, init_db  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    mark = "✅" if ok else "❌"
    print(f"{mark} {name}" + (f"  —— {detail}" if detail else ""))


def png_bytes(color: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # 1x1 透明 PNG
        import base64
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def main() -> int:
    init_db()
    client = TestClient(app)

    # ---------------------------------------------------------------- 登录
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    check("初始账号 admin/admin123 可登录", r.status_code == 200, r.text[:120])
    check("首次登录标记强制改密", r.json().get("must_change_password") is True)
    r = client.post("/api/auth/change-password", json={"new_password": "sbs123456"})
    check("首次登录改密成功", r.status_code == 200 and not r.json()["must_change_password"])

    r = TestClient(app).get("/api/students")
    check("未登录不可访问数据", r.status_code == 401)

    # ------------------------------------------------- 验收 1：四个文件导入
    # 文件名不写死：仓库里不含真实导出表，按列名特征自动识别项目根目录下的文件
    files = find_exports()
    if not files:
        print(HINT)
        return 0
    # 各文件的期望行数从源文件读出来，不硬编码 —— 换一份导出照样能跑
    import pandas as pd
    expected_rows = {}
    for ftype, path in files.items():
        sheet = "报读课程" if ftype == "courses" else 0
        try:
            expected_rows[ftype] = len(pd.read_excel(path, sheet_name=sheet))
        except Exception:
            expected_rows[ftype] = None

    reports = {}
    for expect_type, path in files.items():
        if not path.exists():
            check(f"[1] 找到导出文件 {path.name}", False, "文件不存在")
            continue
        with path.open("rb") as fh:
            r = client.post("/api/imports/preview", files={"file": (path.name, fh.read())})
        ok = r.status_code == 200 and r.json()["file_type"] == expect_type
        check(f"[1] 识别 {path.name} → {expect_type}", ok, r.text[:160])
        if not ok:
            continue
        pv = r.json()
        check(f"[1] 预览前 5 行 + 列名完整（{expect_type}）",
              len(pv["rows"]) == min(5, pv["total_rows"]) and not pv["missing_columns"],
              f"缺列 {pv['missing_columns']}")
        r = client.post("/api/imports/confirm",
                        json={"token": pv["token"], "filename": path.name})
        check(f"[1] 导入 {expect_type} 成功", r.status_code == 200, r.text[:200])
        reports[expect_type] = r.json()

    counts_before = {
        "students": client.get("/api/students?page_size=1").json()["total"],
        "orders": client.get("/api/orders?page_size=1").json()["total"],
        "transactions": client.get("/api/transactions?page_size=1").json()["total"],
    }
    ok_rows = all(expected_rows.get(k) is None or counts_before[k] == expected_rows[k]
                  for k in ("students", "orders", "transactions") if k in files)
    check("[1] 学员/订单/收支入库行数与源文件一致", ok_rows,
          f"入库 {counts_before} / 源文件 {expected_rows}")
    if "courses" in files:
        check("[1] 报读课程全部行入库",
              reports.get("courses", {}).get("accounts_imported") == expected_rows["courses"],
              f"{reports.get('courses', {}).get('accounts_imported')} / {expected_rows['courses']}")

    # "15课时" → 15：从源文件取一行真实值来比对，不写死具体学员
    raw = pd.read_excel(files["courses"], sheet_name="报读课程")
    row = raw.dropna(subset=["学号"]).iloc[0]
    import re as _re
    want_purchased = int(_re.search(r"\d+", str(row["购买数量"])).group())
    want_remaining = int(_re.search(r"\d+", str(row["剩余数量"])).group())
    r = client.get("/api/students", params={"q": str(row["学号"])})
    sid = r.json()["items"][0]["id"]
    detail = client.get(f"/api/students/{sid}").json()
    acc = detail["accounts"][0]
    check(f'[1] "{row["购买数量"]}" 解析为整数 {want_purchased}',
          acc["purchased"] == want_purchased and acc["balance"]["imported"] == want_remaining,
          f"purchased={acc['purchased']} remaining={acc['balance']['imported']}")
    want_expire = str(row["到期时间"]).replace("/", "-")[:10]
    check(f"[1] 到期时间 {row['到期时间']} 解析正确",
          acc["expire_date"] == want_expire, str(acc["expire_date"]))

    # 重复导入同一文件不产生重复数据
    for expect_type, path in files.items():
        if not path.exists():
            continue
        with path.open("rb") as fh:
            pv = client.post("/api/imports/preview",
                             files={"file": (path.name, fh.read())}).json()
        client.post("/api/imports/confirm", json={"token": pv["token"], "filename": path.name})
    counts_after = {
        "students": client.get("/api/students?page_size=1").json()["total"],
        "orders": client.get("/api/orders?page_size=1").json()["total"],
        "transactions": client.get("/api/transactions?page_size=1").json()["total"],
    }
    check("[1] 重复导入同一文件数据不重复", counts_before == counts_after,
          f"{counts_before} → {counts_after}")

    # 回归：读完 Excel 必须释放文件句柄。Windows 不允许删除仍被打开的文件，
    # 句柄不放的话导入后清理临时文件会抛 PermissionError —— 数据已入库却报 500。
    from app.importer import read_excel
    handle_probe = TMP / "handle_probe.xlsx"
    shutil.copy(files["courses"], handle_probe)
    read_excel(handle_probe)
    try:
        handle_probe.unlink()
        released = True
    except OSError as e:
        released = False
        print(f"    句柄未释放：{e}")
    check("[1] 读完 Excel 释放文件句柄（Windows 上不释放会删不掉临时文件）", released)

    # ------------------------------------------- 验收 3：估算口径增减与回退
    meta = client.get("/api/meta").json()
    check("[4.2] 建立了 班级→课程 映射", len(meta["class_course_map"]) > 0,
          f"{len(meta['class_course_map'])} 条")

    target = detail
    class_name = target["accounts"][0]["class_name"]
    course_name = target["accounts"][0]["course_name"]
    base_imported = target["accounts"][0]["balance"]["imported"]

    today = date.today()
    yesterday = today - timedelta(days=1)

    def upload(day: date, text: str = "很好"):
        return client.post("/api/artworks", data={
            "student_id": str(sid), "class_name": class_name, "course_name": course_name,
            "lesson_date": day.isoformat(), "eval_type": "text", "eval_text": text,
            "rating": "优",
        }, files=[("photos", ("a.png", png_bytes(), "image/png"))])

    r1 = upload(yesterday, "昨天的评价")
    check("[5.2] 上传作品+文字评价成功", r1.status_code == 200, r1.text[:200])
    r2 = upload(today, "今天的评价")
    bal = client.get(f"/api/students/{sid}").json()["accounts"][0]["balance"]
    check("[3] 连续两天各一次评价 → 估算比导入少 2",
          bal["estimated"] == base_imported - 2, f"{bal['estimated']} vs {base_imported}")
    check("[6.2] 展开说明文案正确", bal["detail"].startswith(f"导入时 {base_imported}"), bal["detail"])
    check("[6.2] 界面显示『约 N 课时』", bal["display"] == f"约 {base_imported - 2} 课时", bal["display"])

    r3 = upload(today, "今天的第二条评价")
    bal = client.get(f"/api/students/{sid}").json()["accounts"][0]["balance"]
    check("[3] 同一天传两条只少 1（去重按 lesson_date）",
          bal["estimated"] == base_imported - 2, str(bal["estimated"]))

    # 删除当天全部评价 → 回退
    for art_id in (r2.json()["id"], r3.json()["id"]):
        client.delete(f"/api/artworks/{art_id}")
    bal = client.get(f"/api/students/{sid}").json()["accounts"][0]["balance"]
    check("[3] 删除当天全部评价后余额回退",
          bal["estimated"] == base_imported - 1, str(bal["estimated"]))
    timeline = client.get(f"/api/students/{sid}/timeline").json()
    check("[7] 软删除后时间轴不再显示", all(a["id"] != r2.json()["id"] for a in timeline))
    logs = client.get(f"/api/artworks/{r2.json()['id']}/logs").json()
    check("[7] 软删除写入编辑记录", len(logs) == 1 and logs[0]["action"] == "delete")

    # ---------------------------------------------- 验收 4：编辑角标三级
    aid = r1.json()["id"]
    check("[7] 新建时无角标", r1.json()["edit_badge"] == "" and r1.json()["edit_count"] == 0)
    e1 = client.patch(f"/api/artworks/{aid}", data={"eval_text": "第一次修改"})
    check("[4] 第一次修改 → 已编辑", e1.json()["edit_badge"] == "已编辑", e1.json()["edit_badge"])
    e2 = client.patch(f"/api/artworks/{aid}", data={"eval_text": "第二次修改"})
    check("[4] 第二次修改 → 已二次编辑", e2.json()["edit_badge"] == "已二次编辑", e2.json()["edit_badge"])
    e3 = client.patch(f"/api/artworks/{aid}", data={"eval_text": "第三次修改"})
    check("[4] 第三次修改 → 已多次编辑", e3.json()["edit_badge"] == "已多次编辑", e3.json()["edit_badge"])
    logs = client.get(f"/api/artworks/{aid}/logs").json()
    ok_logs = (len(logs) == 3
               and logs[0]["changes"][0]["old"] == "第二次修改"
               and logs[0]["changes"][0]["new"] == "第三次修改"
               and logs[-1]["changes"][0]["old"] == "昨天的评价")
    check("[4] 可见三条完整 old→new 记录（时间倒序）", ok_logs,
          str([(l["changes"][0]["old"], l["changes"][0]["new"]) for l in logs]))
    e4 = client.patch(f"/api/artworks/{aid}", data={"eval_text": "第三次修改"})
    check("[7] 无实际变更不加角标", e4.json()["edit_count"] == 3, str(e4.json()["edit_count"]))

    # 学员信息编辑留痕
    p1 = client.patch(f"/api/students/{sid}", json={"remark": "家长要求周末上课"})
    check("[7] 学员信息编辑出现角标", p1.json()["edit_badge"] == "已编辑")

    # 导入覆盖不算编辑
    path = files["courses"]
    with path.open("rb") as fh:
        pv = client.post("/api/imports/preview", files={"file": (path.name, fh.read())}).json()
    client.post("/api/imports/confirm", json={"token": pv["token"], "filename": path.name})
    st_after = client.get(f"/api/students/{sid}").json()
    check("[7] 导入覆盖不算编辑（角标不变）", st_after["edit_count"] == 1, str(st_after["edit_count"]))

    # ---------------------------------------------- 验收 5：提醒看板
    counts = client.get("/api/alerts/counts").json()
    settings = client.get("/api/settings").json()["settings"]
    renew = client.get("/api/alerts", params={"tab": "renew"}).json()
    expire = client.get("/api/alerts", params={"tab": "expire"}).json()
    absent = client.get("/api/alerts", params={"tab": "absent"}).json()
    check("[5] 三个 Tab 均可返回",
          renew["count"] == counts["renew"] and expire["count"] == counts["expire"]
          and absent["count"] == counts["absent"], str(counts))
    ok_rule = all(i["balance"]["current"] <= int(settings["renew_threshold"]) for i in renew["items"])
    check("[5] 续费预警符合阈值规则（估算口径）", ok_rule)
    ok_absent = all(i["absent_count"] >= int(settings["absent_threshold"]) for i in absent["items"])
    check("[5] 缺课关注符合阈值规则", ok_absent)
    ok_expire = all(0 <= (i["days_to_expire"] or 0) <= int(settings["expire_days"])
                    for i in expire["items"])
    check("[5] 到期预警符合 14 天规则", ok_expire)

    # 手工统计核对
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH)
    manual_absent = conn.execute(
        "SELECT COUNT(*) FROM course_accounts WHERE absent_count >= ?",
        (int(settings["absent_threshold"]),)).fetchone()[0]
    conn.close()
    check("[5] 缺课数字与手工 SQL 统计一致", manual_absent == absent["count"],
          f"SQL={manual_absent} API={absent['count']}")

    # 切换口径
    client.patch("/api/settings", json={"balance_mode": "imported"})
    renew_imported = client.get("/api/alerts", params={"tab": "renew"}).json()
    check("[5] 切换口径后数字随之变化",
          renew_imported["mode"] == "imported", str(renew_imported["mode"]))
    check("[6.1] 导入口径直接显示 remaining_imported",
          client.get(f"/api/students/{sid}").json()["accounts"][0]["balance"]["display"]
          == f"{base_imported} 课时")
    client.patch("/api/settings", json={"balance_mode": "estimated"})

    # 标记已跟进
    if renew["items"]:
        acc_id = renew["items"][0]["course_account_id"]
        f1 = client.post("/api/alerts/follow",
                         json={"course_account_id": acc_id, "alert_type": "renew",
                               "status": "已跟进", "note": "已电话联系"})
        check("[5.3] 可标记已跟进", f1.json()["status"] == "已跟进")
        f2 = client.post("/api/alerts/follow",
                         json={"course_account_id": acc_id, "alert_type": "renew",
                               "status": "待跟进", "note": "家长再考虑"})
        check("[5.3] 跟进状态变更留痕", f2.json()["edit_badge"] == "已编辑", str(f2.json()))

    # ---------------------------------------------- 验收 6：作品集导出
    r = client.get(f"/api/students/{sid}/portfolio")
    html = r.text
    check("[6] 作品集导出成功", r.status_code == 200 and "<!DOCTYPE html>" in html)
    check("[6] 照片以 data URI 内嵌（离线可看）", "data:image/" in html)
    check("[6] 含评价文字与日期",
          "第三次修改" in html and cn_date(yesterday) in html)
    check("[6] 含打印样式（打印即 PDF）", "@media print" in html)
    check("[6] 无任何公网资源引用",
          "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html)

    # 语音评价 + 作品集内嵌
    r = client.post("/api/artworks", data={
        "student_id": str(sid), "class_name": class_name, "course_name": course_name,
        "lesson_date": (today - timedelta(days=3)).isoformat(), "eval_type": "voice",
    }, files=[("audio", ("rec.webm", b"FAKEAUDIODATA" * 20, "audio/webm"))])
    check("[5.2] 语音评价上传成功", r.status_code == 200 and r.json()["eval_audio"],
          r.text[:160])
    html = client.get(f"/api/students/{sid}/portfolio").text
    check("[6] 语音评价在作品集中可播放/可下载",
          "data:audio/webm" in html and "下载语音评价" in html)

    # 媒体文件可访问
    photo_url = r1.json()["photos"][0]
    check("[5.1] 作品照片可通过接口访问",
          client.get(photo_url).status_code == 200, photo_url)
    check("[5.1] 未登录不可访问媒体文件",
          TestClient(app).get(photo_url).status_code == 401)
    from app.media import abs_path as _abs
    blocked = 0
    for bad in ("../../app.db", "200519/../../../secret.key", "../certs/server.key"):
        try:
            _abs(bad)
        except ValueError:
            blocked += 1
    check("[安全] 媒体路径越界被拒", blocked == 3, f"拦截 {blocked}/3")

    # ---------------------------------------------- 老师工作台
    cls = client.get(f"/api/classes/{class_name}/students").json()
    check("[5.2] 班级学员九宫格可用",
          cls["count"] > 0 and cls["items"][0]["balance"] is not None, str(cls["count"]))

    tpls = client.get("/api/eval-templates").json()
    check("[5.2] 评语模板库按分组可用",
          len(tpls) >= 12 and {t["category"] for t in tpls} == {"书法", "美术", "通用"})
    t = client.post("/api/eval-templates",
                    json={"category": "书法", "text": "测试模板", "sort": 99}).json()
    upd = client.patch(f"/api/eval-templates/{t['id']}", json={"text": "测试模板改"}).json()
    check("[5.2] 模板编辑留痕", upd["edit_badge"] == "已编辑")
    client.delete(f"/api/eval-templates/{t['id']}")
    check("[5.2] 模板可删除",
          all(x["id"] != t["id"] for x in client.get("/api/eval-templates").json()))

    # ---------------------------------------------- 偏差报告
    dev = client.get("/api/imports/deviation").json()
    check("[6.3] 偏差报告可查", dev.get("available") is True, str(dev)[:200])
    check("[6.3] 偏差报告列出差值≠0 的学员",
          dev["count"] >= 1 and all(x["diff"] != 0 for x in dev["items"]),
          f"count={dev.get('count')}")
    check("[6.3] 偏差报告不做自动修正",
          client.get(f"/api/students/{sid}").json()["accounts"][0]["balance"]["imported"]
          == base_imported)

    # ---------------------------------------------- 订单/收支只读
    orders = client.get("/api/orders", params={"start": "2026-03-01", "end": "2026-03-15"}).json()
    check("[5.4] 订单按时间筛选 + 合计行",
          orders["total"] > 0 and orders["totals"]["paid"] > 0, str(orders["totals"]))
    txn = client.get("/api/transactions").json()
    t = txn["totals"]
    check("[5.4] 收支合计 收入/支出/净额",
          t["income"] > 0 and t["expense"] > 0
          and abs(t["net"] - (t["income"] - t["expense"])) < 0.01, str(t))

    # ---------------------------------------------- 用户管理 & 备份
    u = client.post("/api/users", json={"username": "teacher1", "password": "abc123",
                                        "name": "测试老师", "role_label": "老师",
                                        "class_bindings": [class_name]}).json()
    check("[2] 可新增账号并绑定班级", u["class_bindings"] == [class_name])
    off = client.patch(f"/api/users/{u['id']}", json={"active": False}).json()
    check("[2] 可停用账号", off["active"] is False)

    b = client.post("/api/backup/run")
    check("[8] 手动备份成功", b.status_code == 200 and b.json()["ok"], b.text[:160])
    status = client.get("/api/settings").json()["backup"]
    check("[8] 设置页显示上次备份时间", bool(status["last_backup_at"]), str(status["last_backup_at"]))
    check("[8] 刚备份完不提示超期黄条", status["stale"] is False)
    b2 = client.post("/api/backup/run").json()
    check("[8] 第二次备份为增量（媒体无变化则不重复打包）",
          b2["media_changed"] == 0, str(b2.get("media_changed")))

    asof = client.get("/api/meta").json()["asof"]
    check("[4] 顶栏显示数据截至时间", bool(asof["courses_asof"]), str(asof))

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：")
        for name in FAIL:
            print("  -", name)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
