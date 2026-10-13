"""수집기 통합 테스트 — 같은 쿼리 지문이 여러 스키마에 있을 때 (실제로 만난 장애의 재현).

LAB_IT=1 .venv/bin/python -m unittest tests.test_collector_it   (실습 환경 필요 · order-db 에 임시 스키마를 만들고 지움)
"""
import datetime as dt
import os
import re
import sys
import unittest

import pymysql

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import collector   # noqa: E402

SRV = dict(host="127.0.0.1", port=3307, user="root", password="lab-root-pw", charset="utf8mb4", autocommit=True,
           cursorclass=pymysql.cursors.DictCursor)
DB = "labtest_dba"


def ddl(name):
    with open(os.path.join(HERE, "..", "mysql", "init", "02_dba.sql"), encoding="utf-8") as f:
        sql = f.read()
    return re.search(rf"CREATE TABLE {name} \(.*?\n\);", sql, re.S).group(0)


@unittest.skipUnless(os.environ.get("LAB_IT") == "1", "LAB_IT=1 일 때만 (실습 DB 필요)")
class SameDigestTwoSchemas(unittest.TestCase):
    def setUp(self):
        self.root = pymysql.connect(**SRV)
        with self.root.cursor() as c:
            c.execute(f"DROP DATABASE IF EXISTS {DB}"); c.execute(f"CREATE DATABASE {DB}")
            c.execute(f"DROP DATABASE IF EXISTS labtest_other"); c.execute("CREATE DATABASE labtest_other")
            c.execute("CREATE TABLE labtest_other.orders (order_id INT PRIMARY KEY)")
            for s in ("shop", "labtest_other"):          # 같은 모양의 쿼리를 두 스키마에서 실행 → 같은 DIGEST 두 행
                c.execute(f"USE {s}"); c.execute("SELECT COUNT(*) FROM orders WHERE order_id = 7"); c.fetchall()
        self.store = pymysql.connect(**dict(SRV, database=DB))
        with self.store.cursor() as c:
            c.execute(ddl("digest_snapshot")); c.execute(ddl("slow_digest_daily"))

    def tearDown(self):
        self.store.close()
        with self.root.cursor() as c:
            c.execute(f"DROP DATABASE IF EXISTS {DB}"); c.execute("DROP DATABASE IF EXISTS labtest_other")
        self.root.close()

    def test_snapshot_and_aggregate(self):
        t1 = dt.datetime(2030, 1, 1, 0, 0, 0)
        collector.snapshot(self.store, "order-db", t1)                   # 실패 전: 중복 키 오류
        collector.aggregate(self.store, "order-db", t1, "2030-01-01")
        with self.root.cursor() as c:                                     # 두 스키마 모두에서 실행 → 하루 한 행에 합산돼야 한다
            for s, n in (("shop", 3), ("labtest_other", 2)):
                c.execute(f"USE {s}")
                for _ in range(n):
                    c.execute("SELECT COUNT(*) FROM orders WHERE order_id = 7"); c.fetchall()
        t2 = t1 + dt.timedelta(days=1)
        collector.snapshot(self.store, "order-db", t2)
        collector.aggregate(self.store, "order-db", t2, "2030-01-02")
        with self.store.cursor() as c:
            c.execute("""SELECT exec_cnt FROM slow_digest_daily WHERE log_date='2030-01-02'
                         AND query_text LIKE 'SELECT COUNT ( * ) FROM `orders` WHERE `order_id` = ?%%'""")
            rows = c.fetchall()
        self.assertEqual(len(rows), 1)                                    # 지문당 하루 한 행
        self.assertEqual(rows[0]["exec_cnt"], 5)                          # shop 3번 + labtest_other 2번

    def test_same_day_twice_accumulates(self):
        """같은 날짜로 두 번 수집하면 두 구간의 실행분을 더한다 (덮어쓰면 그날 값이 줄어든다)."""
        t = dt.datetime(2030, 2, 1)
        collector.snapshot(self.store, "order-db", t); collector.aggregate(self.store, "order-db", t, "2030-01-31")
        for i, n in enumerate((4, 3), 1):
            with self.root.cursor() as c:
                c.execute("USE shop")
                for _ in range(n):
                    c.execute("SELECT COUNT(*) FROM orders WHERE order_id = 8"); c.fetchall()
            ti = t + dt.timedelta(hours=i)
            collector.snapshot(self.store, "order-db", ti); collector.aggregate(self.store, "order-db", ti, "2030-02-01")
        with self.store.cursor() as c:
            c.execute("""SELECT exec_cnt FROM slow_digest_daily WHERE log_date='2030-02-01'
                         AND query_text LIKE 'SELECT COUNT ( * ) FROM `orders` WHERE `order_id` = ?%%'""")
            self.assertEqual(c.fetchone()["exec_cnt"], 7)


if __name__ == "__main__":
    unittest.main()
