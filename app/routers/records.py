"""订单 / 收支页（规格书 §5.4）：纯只读表格 + 时间范围筛选 + 合计行。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Order, Transaction, User
from ..security import current_user
from ..utils import dt_str, parse_datetime

router = APIRouter(prefix="/api", tags=["records"])


def _range(query, column, start: str, end: str):
    s = parse_datetime(start)
    e = parse_datetime(end)
    if s:
        query = query.filter(column >= s)
    if e:
        # 结束日期含当天
        e = e.replace(hour=23, minute=59, second=59) if e.hour == 0 and e.minute == 0 else e
        query = query.filter(column <= e)
    return query


@router.get("/orders")
def list_orders(start: str = Query(""), end: str = Query(""), q: str = Query(""),
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                db: Session = Depends(get_db), _: User = Depends(current_user)):
    query = _range(db.query(Order), Order.created_time, start, end)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Order.student_name.like(like)) | (Order.order_no.like(like))
                             | (Order.phone.like(like)) | (Order.purchase_item.like(like)))
    total = query.count()
    sums = query.with_entities(
        func.coalesce(func.sum(Order.due_amount), 0.0),
        func.coalesce(func.sum(Order.paid_amount), 0.0),
        func.coalesce(func.sum(Order.owed_amount), 0.0),
    ).one()
    rows = (query.order_by(Order.created_time.desc(), Order.id.desc())
                 .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "total": total, "page": page, "page_size": page_size,
        "totals": {"due": round(sums[0], 2), "paid": round(sums[1], 2), "owed": round(sums[2], 2)},
        "items": [{
            "id": o.id, "order_no": o.order_no, "serial_no": o.serial_no,
            "student_name": o.student_name, "phone": o.phone, "order_type": o.order_type,
            "purchase_item": o.purchase_item, "due_amount": o.due_amount,
            "paid_amount": o.paid_amount, "owed_amount": o.owed_amount,
            "order_source": o.order_source, "performance_owner": o.performance_owner,
            "operator": o.operator, "created_time": dt_str(o.created_time),
            "handled_time": o.handled_time, "last_pay_time": o.last_pay_time,
            "prepay_status": o.prepay_status, "order_status": o.order_status,
            "remark": o.remark, "message": o.message, "student_creator": o.student_creator,
        } for o in rows],
    }


@router.get("/transactions")
def list_transactions(start: str = Query(""), end: str = Query(""), q: str = Query(""),
                      io_type: str = Query(""),
                      page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                      db: Session = Depends(get_db), _: User = Depends(current_user)):
    query = _range(db.query(Transaction), Transaction.created_time, start, end)
    if io_type:
        query = query.filter(Transaction.io_type == io_type)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Transaction.payer.like(like)) | (Transaction.item.like(like))
                             | (Transaction.related_order_no.like(like))
                             | (Transaction.operator.like(like)))
    total = query.count()
    income = query.filter(Transaction.io_type == "收入").with_entities(
        func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0
    # 导出文件里支出行的金额本身是负数，这里统一按绝对值展示，净额 = 收入 − 支出
    expense = abs(query.filter(Transaction.io_type == "支出").with_entities(
        func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0)
    rows = (query.order_by(Transaction.created_time.desc(), Transaction.id.desc())
                 .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "total": total, "page": page, "page_size": page_size,
        "totals": {"income": round(income, 2), "expense": round(expense, 2),
                   "net": round(income - expense, 2)},
        "items": [{
            "id": t.id, "created_time": dt_str(t.created_time), "item": t.item,
            "io_type": t.io_type, "status": t.status, "amount": t.amount,
            "pay_method": t.pay_method, "account": t.account, "handled_date": t.handled_date,
            "operator": t.operator, "related_order_no": t.related_order_no, "payer": t.payer,
            "pay_serial": t.pay_serial, "fail_reason": t.fail_reason, "remark": t.remark,
            "campus": t.campus,
        } for t in rows],
    }
