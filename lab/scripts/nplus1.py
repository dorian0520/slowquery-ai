"""15강: ORM 이 만드는 N+1 쿼리 재현과 해결 비교.

VIP 회원 100명의 최근 주문 3건을 화면에 보여 준다고 가정한다.
python3 nplus1.py
"""
import time
import pymysql

conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="lab-root-pw",
                       database="shop", autocommit=True)
cur = conn.cursor()
cur.execute("ALTER TABLE orders ADD INDEX ix_tmp_user_ordered (user_id, ordered_at)")


def digest_count():
    cur.execute("""SELECT IFNULL(SUM(COUNT_STAR),0) FROM performance_schema.events_statements_summary_by_digest
                   WHERE SCHEMA_NAME='shop' AND DIGEST_TEXT LIKE 'SELECT `order_id` , `amount` , `ordered_at` FROM `orders`%'""")
    return int(cur.fetchone()[0])


# ① N+1: 회원 목록 1번 + 회원마다 주문 1번
before = digest_count()
t = time.perf_counter()
cur.execute("SELECT user_id FROM users WHERE grade = 'VIP' ORDER BY user_id LIMIT 100")
users = [r[0] for r in cur.fetchall()]
for uid in users:
    cur.execute("SELECT order_id, amount, ordered_at FROM orders WHERE user_id = %s ORDER BY ordered_at DESC LIMIT 3", (uid,))
    cur.fetchall()
n1 = time.perf_counter() - t
print(f"① N+1   : 쿼리 {1 + len(users)}번, {n1 * 1000:.0f} ms, digest 실행 증가 {digest_count() - before}")

# ② 한 번에: IN 으로 묶고, 회원별 3건은 ROW_NUMBER() 로 SQL 에서 고른다
t = time.perf_counter()
cur.execute("SELECT user_id FROM users WHERE grade = 'VIP' ORDER BY user_id LIMIT 100")
users = [r[0] for r in cur.fetchall()]
cur.execute(f"""SELECT user_id, order_id, amount, ordered_at FROM (
                  SELECT user_id, order_id, amount, ordered_at,
                         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ordered_at DESC) rn
                  FROM orders WHERE user_id IN ({','.join(map(str, users))})) x WHERE rn <= 3""")
rows = cur.fetchall()
one = time.perf_counter() - t
print(f"② 한 번에: 쿼리 2번, {one * 1000:.0f} ms, 결과 {len(rows)}행")

cur.execute("ALTER TABLE orders DROP INDEX ix_tmp_user_ordered")
conn.close()
