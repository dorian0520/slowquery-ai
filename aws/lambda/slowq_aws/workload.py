"""workload (선택): 샘플 DB 에 느린 쿼리와 빠른 쿼리를 섞어 실행한다 (lab/scripts/workload.py 와 같은 쿼리).

입력: {"scale": 1.0, "only": ["coupon_usage", ...]} — 모두 선택. 남은 실행 시간이 적으면 중간에 멈춘다.
읽기 전용 계정(slowq_workload, 서비스 스키마 SELECT 만)으로 실행한다.
"""
import random

from . import common

QUERIES = [
    ("user_recent_orders",
     "SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = %s ORDER BY ordered_at DESC LIMIT 20",
     lambda: (random.randint(1, 200000),), 40),
    ("coupon_usage",
     "SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = %s",
     lambda: (f"CPN{random.randint(0, 499)}",), 15),
    ("daily_status_count",
     "SELECT status, COUNT(*) FROM orders WHERE ordered_at >= %s AND ordered_at < %s + INTERVAL 1 DAY GROUP BY status",
     lambda: (f"2025-0{random.randint(1, 9)}-1{random.randint(0, 9)}",) * 2, 10),
    ("deep_offset_paging",
     "SELECT order_id, user_id, amount FROM orders ORDER BY ordered_at DESC LIMIT %s, 20",
     lambda: (random.choice([100000, 300000, 500000]),), 6),
    ("vip_monthly_sales",
     "SELECT u.grade, SUM(o.amount) FROM orders o JOIN users u ON u.user_id = o.user_id "
     "WHERE u.grade = 'VIP' AND o.ordered_at >= %s GROUP BY u.grade",
     lambda: (f"2025-0{random.randint(5, 9)}-01",), 4),
    ("email_search",
     "SELECT user_id, email FROM users WHERE email LIKE %s LIMIT 10",
     lambda: (f"%{random.randint(1000, 9999)}@%",), 20),
    ("order_by_pk",  # 빠른 쿼리 (대조군)
     "SELECT * FROM orders WHERE order_id = %s",
     lambda: (random.randint(1, 2000000),), 300),
]
SAFETY_MS = 30000


def run(conn, scale=1.0, only=None, time_left=lambda: 10 ** 9):
    done = {}
    with conn.cursor() as cur:
        for name, sql, args, n in QUERIES:
            if only and name not in only:
                continue
            for _ in range(max(1, int(n * scale))):
                if time_left() < SAFETY_MS:
                    done["stopped_early"] = True
                    return done
                cur.execute(sql, args())
                cur.fetchall()
                done[name] = done.get(name, 0) + 1
    return done


def handler(event, context):
    event = event or {}
    conn = common.connect(common.env("TARGET_HOST", required=True), common.env("WORKLOAD_SECRET_ARN", required=True),
                          common.env("SHOP_DB", "shop"))
    try:
        r = run(conn, float(event.get("scale", common.env("WORKLOAD_SCALE", "1.0"))), event.get("only"),
                context.get_remaining_time_in_millis if context else (lambda: 10 ** 9))
    finally:
        conn.close()
    common.log.info("workload %s", r)
    return r
