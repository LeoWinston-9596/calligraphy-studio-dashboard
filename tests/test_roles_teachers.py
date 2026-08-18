"""角色分级权限 + 老师班级自动匹配 自测。

    python tests/test_roles_teachers.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TMP = Path(tempfile.mkdtemp(prefix="sbs_roles_"))
import app.config as config  # noqa: E402

config.DATA_DIR = TMP / "data"
config.MEDIA_DIR = config.DATA_DIR / "media"
config.CERT_DIR = config.DATA_DIR / "certs"
config.UPLOAD_TMP_DIR = config.DATA_DIR / "uploads_tmp"
config.BACKUP_DIR = TMP / "backups"
config.DB_PATH = config.DATA_DIR / "app.db"
config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"
config.ensure_dirs()

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from _data import HINT, find_exports, import_all  # noqa: E402
from app.main import app, init_db  # noqa: E402

PASS, FAIL, SKIP = [], [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'✅' if ok else '❌'} {name}" + (f"  —— {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    SKIP.append(name)
    print(f"⏭  {name}  —— {why}")


def login(username: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def main() -> int:
    init_db()
    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    admin.post("/api/auth/change-password", json={"new_password": "admin123456"})

    exports = find_exports()
    if "students" not in exports or "courses" not in exports:
        print(HINT)
        return 0
    import_all(admin, exports, only=["students", "courses"])

    # ---------------------------------------------- 老师↔班级自动匹配
    # 老师名一律从接口取，不硬编码 —— 仓库里没有真实数据，也不该出现真实姓名
    teachers = sorted(admin.get("/api/users/teachers").json(),
                      key=lambda t: -t["class_count"])
    check("[匹配] 从导入表推导出老师名单", len(teachers) >= 1,
          f"{len(teachers)} 位：{[t['name'] for t in teachers][:3]}")
    if not teachers:
        print("导出表里没有「跟进人」数据，后续用例无法进行")
        return 1

    T1 = teachers[0]["name"]                      # 带班最多的老师
    T2 = teachers[1]["name"] if len(teachers) > 1 else None
    T3 = teachers[2]["name"] if len(teachers) > 2 else T2
    n1 = teachers[0]["class_count"]
    check(f"[匹配] 主力老师带 {n1} 个班", n1 >= 1, f"{T1}: {n1} 班")

    # 去掉「老师」后缀也要能对上
    m = admin.get("/api/users/match-teacher",
                  params={"name": T1.removesuffix("老师") or T1}).json()
    check("[匹配] 按姓名模糊对到完整老师名",
          T1 in m["matched"] and len(m["classes"]) == n1, str(m["matched"]))

    # 创建老师账号：不填班级，自动匹配
    r = admin.post("/api/users", json={
        "username": "t1", "password": "t1123456", "name": T1, "role_label": "老师",
    })
    check("[匹配] 建账号不手选班级即可创建", r.status_code == 200, r.text[:160])
    xu = r.json()
    check("[匹配] 自动勾中导入表老师身份", xu["teacher_names"] == [T1], str(xu["teacher_names"]))
    check(f"[匹配] 自动带出 {n1} 个班（无需手选）",
          len(xu["effective_classes"]) == n1, str(len(xu["effective_classes"])))

    xu_client = login("t1", "t1123456")
    meta = xu_client.get("/api/meta").json()
    check("[匹配] 老师登录后「我的班级」直接可用",
          len(meta["my_classes"]) == n1 and meta["auto_bind_classes"] is True,
          str(len(meta["my_classes"])))

    # 关键场景：教务 App 新开班级 → 重新导入 → 自动归属，不用回来手选
    src = exports["courses"]
    df = pd.read_excel(src, sheet_name="报读课程")
    new_row = df.iloc[0].copy()
    new_row["所在班级"] = "__测试新开班级__"
    new_row["跟进人"] = T1
    df2 = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    tmp_xlsx = TMP / "新班级.xlsx"
    df2.to_excel(tmp_xlsx, sheet_name="报读课程", index=False)

    with tmp_xlsx.open("rb") as fh:
        pv = admin.post("/api/imports/preview", files={"file": (tmp_xlsx.name, fh.read())}).json()
    admin.post("/api/imports/confirm", json={"token": pv["token"], "filename": tmp_xlsx.name})

    meta2 = xu_client.get("/api/meta").json()
    check("[匹配] 新开班级导入后自动出现在老师的「我的班级」",
          "__测试新开班级__" in meta2["my_classes"],
          f"{len(meta['my_classes'])} → {len(meta2['my_classes'])} 个班")

    # 一个账号绑多个身份 → 班级取并集
    if T2:
        admin.patch(f"/api/users/{xu['id']}", json={"teacher_names": [T1, T2]})
        both = xu_client.get("/api/meta").json()["my_classes"]
        only_1 = admin.get("/api/users/match-teacher", params={"name": T1}).json()["classes"]
        only_2 = admin.get("/api/users/match-teacher", params={"name": T2}).json()["classes"]
        check("[多身份] 绑两个身份时班级取并集",
              set(both) == set(only_1) | set(only_2)
              and len(both) >= max(len(only_1), len(only_2)),
              f"{len(only_1)} ∪ {len(only_2)} = {len(both)}")
        admin.patch(f"/api/users/{xu['id']}", json={"teacher_names": [T1]})
    else:
        skip("[多身份] 绑两个身份时班级取并集", "导出表里只有一位跟进人")

    # 手动模式下不会自动跟随
    pinned = xu_client.get("/api/meta").json()["my_classes"][0]
    admin.patch(f"/api/users/{xu['id']}", json={"auto_bind_classes": False,
                                                "class_bindings": [pinned]})
    meta3 = xu_client.get("/api/meta").json()
    check("[匹配] 手动模式只认勾选的班", meta3["my_classes"] == [pinned],
          str(meta3["my_classes"]))
    admin.patch(f"/api/users/{xu['id']}", json={"auto_bind_classes": True})

    # ---------------------------------------------- 跟进人按班级多选
    # 挑一个「有班级且有跟进人」的学员，不指定具体是谁
    # 必须挑「在报读课程表里真实存在」的班级：后面要改写那张表再导入，
    # 如果挑到前面用例注入的临时班级，改写压根落不到它头上。
    real_classes = set(pd.read_excel(exports["courses"],
                                     sheet_name="报读课程")["所在班级"].dropna().astype(str))
    target = None
    listing = admin.get("/api/students", params={"page_size": 200}).json()["items"]
    for item in listing:
        d = admin.get(f"/api/students/{item['id']}").json()
        rows = [c for c in d["class_teachers"]
                if c["class_name"] in real_classes and c["teachers"]]
        if rows:
            target, detail, first_class = item["id"], d, rows[0]["class_name"]
            break
    if target is None:
        skip("[跟进人] 按班级多选", "导出数据里没有同时带班级和跟进人的学员")
    else:
        sid = target
        row0 = next(c for c in detail["class_teachers"] if c["class_name"] == first_class)
        imported_teacher = row0["teachers"][0]
        # 另找一位不同的老师用来做「手工添加」
        extra = next((t["name"] for t in teachers if t["name"] != imported_teacher),
                     "__手工老师__")

        check("[跟进人] 学员详情按班列出跟进人", len(detail["class_teachers"]) >= 1)
        check("[跟进人] 导入值已落到班级上", len(row0["teachers"]) >= 1, str(row0["teachers"]))

        # 一个学员在不同班跟不同老师
        pair = [imported_teacher, extra]
        r = admin.patch(f"/api/students/{sid}/class-teachers",
                        json={"class_name": first_class, "teachers": pair})
        check("[跟进人] 单个班可设多个跟进人", r.json()["teachers"] == pair, r.text[:120])
        check("[跟进人] 修改后学员层汇总包含两人",
              set(r.json()["follow_up_persons"]) >= set(pair),
              str(r.json()["follow_up_persons"]))
        check("[跟进人] 修改跟进人出现编辑角标",
              r.json()["student_edit_badge"] == "已编辑", str(r.json()["student_edit_badge"]))

        logs = admin.get(f"/api/students/{sid}/logs").json()
        chg = logs[0]["changes"][0]
        check("[跟进人] 留痕记录带班级名与 old→new",
              first_class in chg["field_label"] and chg["new"] == pair, str(chg))

        r2 = admin.patch(f"/api/students/{sid}/class-teachers",
                         json={"class_name": first_class, "teachers": pair})
        check("[跟进人] 无变更不加角标", r2.json()["changed"] == [], str(r2.json()["changed"]))

        # 手工加的老师必须活过重新导入
        src = exports["courses"]
        with src.open("rb") as fh:
            pv = admin.post("/api/imports/preview",
                            files={"file": (src.name, fh.read())}).json()
        admin.post("/api/imports/confirm",
                   json={"token": pv["token"], "filename": src.name})
        after = admin.get(f"/api/students/{sid}").json()
        kept = next(c for c in after["class_teachers"] if c["class_name"] == first_class)
        check("[跟进人] 手工加的老师在重新导入后仍在",
              set(kept["teachers"]) >= set(pair), str(kept["teachers"]))

        # 教务 App 里把跟进人改掉 → 替换导入值、保留手工值
        swapped = "__换过的跟进人__"
        df3 = pd.read_excel(src, sheet_name="报读课程")
        no_col = "学号"
        df3.loc[df3[no_col].astype(str) == str(detail["student_no"]), "跟进人"] = swapped
        changed_xlsx = TMP / "改跟进人.xlsx"
        df3.to_excel(changed_xlsx, sheet_name="报读课程", index=False)
        with changed_xlsx.open("rb") as fh:
            pv = admin.post("/api/imports/preview",
                            files={"file": (changed_xlsx.name, fh.read())}).json()
        admin.post("/api/imports/confirm",
                   json={"token": pv["token"], "filename": changed_xlsx.name})
        after2 = admin.get(f"/api/students/{sid}").json()
        row2 = next(c for c in after2["class_teachers"] if c["class_name"] == first_class)
        check("[跟进人] 导入值变更时替换旧导入值、保留手工值",
              swapped in row2["teachers"] and imported_teacher not in row2["teachers"]
              and extra in row2["teachers"], str(row2["teachers"]))

        # 按跟进人筛选：通过班级关联也要能筛到
        got = admin.get("/api/students", params={"follow_up_person": extra}).json()
        check("[跟进人] 列表按跟进人筛选命中班级关联的学员",
              any(x["id"] == sid for x in got["items"]), f"共 {got['total']} 人")

    # ---------------------------------------------- 角色分级
    admin.post("/api/users", json={"username": "jw", "password": "jw123456",
                                   "name": "教务账号", "role_label": "教务"})
    admin.post("/api/users", json={"username": "xz2", "password": "xz123456",
                                   "name": "校长账号", "role_label": "校长"})
    jw = login("jw", "jw123456")
    ls = login("t1", "t1123456")

    me_admin = admin.get("/api/auth/me").json()
    check("[权限] 校长可创建 校长/教务/老师",
          me_admin["permissions"]["creatable_roles"] == ["校长", "教务", "老师"],
          str(me_admin["permissions"]["creatable_roles"]))
    me_jw = jw.get("/api/auth/me").json()
    check("[权限] 教务只能创建 教务/老师",
          me_jw["permissions"]["creatable_roles"] == ["教务", "老师"],
          str(me_jw["permissions"]["creatable_roles"]))
    me_ls = ls.get("/api/auth/me").json()
    check("[权限] 老师不能创建账号",
          me_ls["permissions"]["can_create_user"] is False
          and me_ls["permissions"]["creatable_roles"] == [])

    r = ls.post("/api/users", json={"username": "x1", "password": "x1123456", "role_label": "老师"})
    check("[权限] 老师建账号被拒绝", r.status_code == 403, r.text[:100])

    r = jw.post("/api/users", json={"username": "x2", "password": "x2123456", "role_label": "校长"})
    check("[权限] 教务不能创建校长", r.status_code == 403, r.text[:100])

    second = T2 or T1
    # 带班数要现取：前面的用例可能已经给这位老师手工加过班，开头缓存的数字会过期
    n2 = len(admin.get("/api/users/match-teacher",
                       params={"name": second}).json()["classes"])
    r = jw.post("/api/users", json={"username": "t2", "password": "t2123456",
                                    "name": second, "role_label": "老师"})
    check("[权限] 教务可以创建老师", r.status_code == 200, r.text[:100])
    xie = r.json()
    check("[匹配] 教务建的老师账号也自动匹配班级",
          xie["teacher_names"] == [second] and len(xie["effective_classes"]) == n2,
          f"{xie['teacher_names']} {len(xie['effective_classes'])}")

    users = admin.get("/api/users").json()["items"]
    ids = {u["username"]: u["id"] for u in users}

    # 停用规则
    r = ls.patch(f"/api/users/{ids['t2']}", json={"active": False})
    check("[权限] 老师不能停用其他老师", r.status_code == 403, r.text[:100])
    r = ls.patch(f"/api/users/{ids['jw']}", json={"active": False})
    check("[权限] 老师不能停用教务", r.status_code == 403, r.text[:100])

    r = jw.patch(f"/api/users/{ids['t2']}", json={"active": False})
    check("[权限] 教务可以停用老师", r.status_code == 200 and r.json()["active"] is False,
          r.text[:100])
    r = jw.patch(f"/api/users/{ids['xz2']}", json={"active": False})
    check("[权限] 教务不能停用校长", r.status_code == 403, r.text[:100])
    r = jw.patch(f"/api/users/{ids['jw']}", json={"active": False})
    check("[权限] 不能停用自己", r.status_code == 400, r.text[:100])

    r = admin.patch(f"/api/users/{ids['jw']}", json={"active": False})
    check("[权限] 校长可以停用教务", r.status_code == 200 and r.json()["active"] is False,
          r.text[:100])
    r = admin.patch(f"/api/users/{ids['t1']}", json={"active": False})
    check("[权限] 校长可以停用老师", r.status_code == 200, r.text[:100])
    admin.patch(f"/api/users/{ids['t1']}", json={"active": True})

    # 角色提升限制（先把上面停用的教务恢复，否则会话已失效）
    admin.patch(f"/api/users/{ids['jw']}", json={"active": True})
    jw = login("jw", "jw123456")
    r = jw.patch(f"/api/users/{ids['t1']}", json={"role_label": "校长"})
    check("[权限] 教务不能把别人提成校长", r.status_code == 403, r.text[:100])
    r = jw.patch(f"/api/users/{ids['t1']}", json={"role_label": "教务"})
    check("[权限] 教务可以把老师提成教务（同级）", r.status_code == 200, r.text[:100])
    admin.patch(f"/api/users/{ids['t1']}", json={"role_label": "老师"})

    r = admin.patch(f"/api/users/{ids['jw']}", json={"active": False})
    check("[权限] 停用后账号立即失效",
          TestClient(app).post("/api/auth/login",
                               json={"username": "jw", "password": "jw123456"}).status_code == 403)

    # 业务数据不受角色限制（规格书原则未变）
    r = ls.get("/api/students", params={"page_size": 1})
    check("[权限] 老师仍可查看全部学员数据", r.status_code == 200 and r.json()["total"] > 0)
    sid = ls.get("/api/students", params={"page_size": 1}).json()["items"][0]["id"]
    r = ls.patch(f"/api/students/{sid}", json={"remark": "老师改的备注"})
    # 这个学员前面可能已被改过，所以只断言"有角标"，不锁定具体次数
    check("[权限] 老师仍可编辑业务数据（靠留痕追溯）",
          r.status_code == 200 and bool(r.json()["edit_badge"]), r.text[:100])

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项" +
          (f"，跳过 {len(SKIP)} 项" if SKIP else ""))
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
