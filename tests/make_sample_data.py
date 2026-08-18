#!/usr/bin/env python3
"""生成合成的教务导出表，供 CI 和新克隆的仓库跑完整测试。

    python tests/make_sample_data.py [输出目录]

真实导出表含学员姓名、家长手机号和住址，永远不会进仓库；但没有数据的话
测试会跳过九成用例，CI 就变成"绿色但什么都没测"。所以这里按真实导出的
**列结构**造一份全是假数据的表，让断言真正跑起来。

姓名一律 学员NN / 张老师，手机号一律 130xxxxxxxx —— 一眼可辨的假数据。

Generates synthetic exports so CI (and a fresh clone) can run the full suite.
Real exports contain student PII and are never committed; without data the
suites skip ~90% of their assertions, which would make a green badge meaningless.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

TEACHERS = ["张老师", "李老师", "王老师"]
CLASSES = [
    ("周一4:40-6:10书法教室1", "硬笔书法", "书法班"),
    ("周三4:00-5:30书法教室2", "软笔书法", "书法班"),
    ("周六上午美术班", "造型课（一二年级）", "美术班"),
    ("2026暑假下午书法班", "暑假班·书法", "暑假班"),
    ("2026暑假美术班", "暑假班·美术", "暑假班"),
]
N_STUDENTS = 40

STUDENT_COLS = [
    "学员姓名", "性别", "手机号身份", "手机号", "微信绑定状态", "绑卡状态", "人脸采集状态",
    "备用手机号身份", "备用手机号", "来源", "出生日期", "所在班级", "年龄", "年级", "学号",
    "学校", "跟进人", "学管师", "住址", "标签", "备注", "学员创建人", "创建时间",
]
ORDER_COLS = [
    "订单号", "流水号（支付/退款）", "学生姓名", "手机号", "订单类型", "购买项目",
    "应收/应退", "实收/实退", "欠费金额", "订单来源", "业绩归属人", "经办人", "创建时间",
    "经办时间", "上次推送时间", "最近支付时间", "先学后付订单状态", "订单状态", "备注",
    "留言", "学生创建人",
]
TXN_COLS = [
    "创建时间", "收支项目", "收支类型", "状态", "收支金额", "支付方式", "收支账户",
    "经办日期", "经办人", "关联订单号", "收付款人", "支付流水号", "交易失败原因", "备注",
    "校区名称",
]


def student_rows() -> list[dict]:
    rows = []
    for i in range(N_STUDENTS):
        cls_i = i % len(CLASSES)
        # 每 7 个学员里有 1 个报两个班 —— 用来覆盖「一个学员多个班」的逻辑
        classes = [CLASSES[cls_i][0]]
        if i % 7 == 0:
            classes.append(CLASSES[(cls_i + 1) % len(CLASSES)][0])
        rows.append({
            "学员姓名": f"学员{i + 1:02d}",
            "性别": "未知",
            "手机号身份": "妈妈" if i % 2 else "本人",
            "手机号": f"130{i + 1:08d}",
            "微信绑定状态": "已绑定" if i % 3 else "未绑定",
            "绑卡状态": "未绑定",
            "人脸采集状态": "未采集",
            "备用手机号身份": None,
            "备用手机号": None,
            "来源": None,
            "出生日期": None,
            # 多个班用分号分隔，和真实导出一致
            "所在班级": ";".join(classes),
            "年龄": None,
            "年级": None,
            "学号": 200000 + i + 1,
            "学校": None,
            # 留几个没有跟进人的，覆盖「跟进人为空」的分支
            "跟进人": TEACHERS[i % len(TEACHERS)] if i % 5 else None,
            "学管师": None,
            "住址": None,
            "标签": None,
            "备注": None,
            "学员创建人": TEACHERS[i % len(TEACHERS)],
            "创建时间": (datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d %H:%M"),
        })
    return rows


def course_rows(students: list[dict]) -> list[dict]:
    rows = []
    expire = date.today() + timedelta(days=10)     # 近期到期，覆盖到期预警
    far = date.today() + timedelta(days=200)
    for i, st in enumerate(students):
        for cls_name in str(st["所在班级"]).split(";"):
            cls = next(c for c in CLASSES if c[0] == cls_name)
            purchased = 15 + (i % 3) * 5
            consumed = 5 + (i % 6)
            remaining = purchased - consumed
            rows.append({
                "学员姓名": st["学员姓名"],
                "手机号身份": st["手机号身份"],
                "手机号": st["手机号"],
                "所在班级": cls_name,
                "课程名称": cls[1],
                "课程类型": "一对多",
                # 真实导出就是这种「N课时」写法，解析必须还原成整数
                "购买数量": f"{purchased}课时",
                "赠送数量": f"{i % 2}课时",
                "消耗数量": f"{consumed}课时",
                "退转数量": "0课时",
                "剩余数量": f"{remaining}课时",
                "超上数量": "0课时",
                "课消金额": round(consumed * 80.0, 2),
                "剩余课消金额": round(remaining * 80.0, 2),
                "缺课次数": i % 4,             # 覆盖缺课关注阈值
                "跟进人": st["跟进人"],
                "学管师": None,
                "到期时间": (expire if i % 4 == 0 else far).strftime("%Y/%m/%d"),
                "性别": st["性别"],
                "微信绑定状态": st["微信绑定状态"],
                "绑卡状态": st["绑卡状态"],
                "人脸采集状态": st["人脸采集状态"],
                "备用手机号身份": None, "备用手机号": None, "来源": None, "出生日期": None,
                "年龄": None, "年级": None,
                "学号": st["学号"],
                "学校": None, "住址": None, "标签": None, "备注": None,
                "学员创建人": st["学员创建人"],
                "停课时间": None, "复课时间": None, "停课备注": None,
            })
    return rows


def order_rows(students: list[dict]) -> list[dict]:
    rows = []
    for i, st in enumerate(students):
        for k in range(2):
            created = datetime(2026, 3, 1) + timedelta(days=i, hours=k)
            paid = 800.0 + (i % 5) * 200
            rows.append({
                "订单号": f"{created:%Y%m%d%H%M%S}{i:04d}{k}",
                "流水号（支付/退款）": None,
                "学生姓名": st["学员姓名"],
                "手机号": st["手机号"],
                "订单类型": "报名/续费" if k == 0 else "转课",
                "购买项目": "硬笔书法 单价(100.00元/课时)",
                "应收/应退": paid, "实收/实退": paid, "欠费金额": 0.0,
                "订单来源": "机构创建",
                "业绩归属人": TEACHERS[i % len(TEACHERS)],
                "经办人": TEACHERS[(i + 1) % len(TEACHERS)],
                "创建时间": created.strftime("%Y-%m-%d %H:%M"),
                "经办时间": created.strftime("%Y-%m-%d"),
                "上次推送时间": "-", "最近支付时间": created.strftime("%Y-%m-%d %H:%M"),
                "先学后付订单状态": "-", "订单状态": "已支付",
                "备注": "-", "留言": "-",
                "学生创建人": st["学员创建人"],
            })
    return rows


def txn_rows(students: list[dict]) -> list[dict]:
    rows = []
    for i, st in enumerate(students):
        created = datetime(2026, 3, 1) + timedelta(days=i)
        income = i % 8 != 0
        rows.append({
            "创建时间": created.strftime("%Y-%m-%d %H:%M"),
            "收支项目": "报名/续费" if income else "退课",
            "收支类型": "收入" if income else "支出",
            "状态": "已确认",
            # 真实导出里支出金额是负数，合计逻辑依赖这一点
            "收支金额": 899.0 if income else -199.0,
            "支付方式": "微信",
            "收支账户": None,
            "经办日期": created.strftime("%Y-%m-%d"),
            "经办人": TEACHERS[i % len(TEACHERS)],
            "关联订单号": f"{created:%Y%m%d%H%M%S}{i:04d}0",
            "收付款人": st["学员姓名"],
            "支付流水号": "-", "交易失败原因": None, "备注": None,
            "校区名称": "示例书画室",
        })
    return rows


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    out.mkdir(parents=True, exist_ok=True)

    students = student_rows()
    courses = course_rows(students)
    orders = order_rows(students)
    txns = txn_rows(students)

    pd.DataFrame(students, columns=STUDENT_COLS).to_excel(
        out / "sample-在读学员名单.xlsx", index=False)
    # 课程表必须是「报读课程」这个 sheet 名，真实导出还有个多余的 hidden sheet
    with pd.ExcelWriter(out / "sample-学生报读课程.xlsx") as w:
        pd.DataFrame(courses).to_excel(w, sheet_name="报读课程", index=False)
        pd.DataFrame({"zht通用课程": ["示例课程"]}).to_excel(w, sheet_name="hidden", index=False)
    pd.DataFrame(orders, columns=ORDER_COLS).to_excel(
        out / "sample-订单导出.xlsx", index=False)
    pd.DataFrame(txns, columns=TXN_COLS).to_excel(
        out / "sample-收支明细.xlsx", index=False)

    print(f"已生成合成数据到 {out}")
    print(f"  学员 {len(students)} 人 · 课时账户 {len(courses)} 条 · "
          f"订单 {len(orders)} 条 · 收支 {len(txns)} 条")
    print(f"  老师：{'、'.join(TEACHERS)}（全部为假数据）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
