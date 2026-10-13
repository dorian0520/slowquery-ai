"""실습용 부하 발생기: 느린 쿼리와 빠른 쿼리를 섞어 실행한다.

python3 workload.py --cluster shop-db --scale 1.0
"""
import argparse, random
from common import connect

# (이름, SQL, 기본 실행 횟수) — 인덱스가 없어서 느린 쿼리들이 강의 실습 대상
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


def run(cluster, scale, only=None):
    conn = connect(cluster, user="root", password="lab-root-pw", db="shop")
    with conn.cursor() as cur:
        for name, sql, args, n in QUERIES:
            if only and name not in only:
                continue
            for _ in range(max(1, int(n * scale))):
                cur.execute(sql, args())
                cur.fetchall()
    conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cluster", default="shop-db")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--only", nargs="*")
    a = p.parse_args()
    run(a.cluster, a.scale, a.only)
