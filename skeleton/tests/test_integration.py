"""실습 DB(order-db, 3307)로 하는 통합 테스트. 별도 스키마 slowq_it 를 만들고 끝나면 지운다.

SLOWQ_IT=1 python3 -m unittest tests.test_integration      (실습 환경이 떠 있을 때만)
"""
import os
import re
import unittest
from unittest import mock

from slowq import collect, detect, tickets
from slowq.config import load
from slowq.db import connect, apply_schema

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IT = os.environ.get("SLOWQ_IT") == "1"
SRV = dict(host="127.0.0.1", port=3307, user="root", password=os.environ.get("SLOWQ_IT_PASSWORD", "lab-root-pw"))


@unittest.skipUnless(IT, "SLOWQ_IT=1 일 때만 (실습 DB 필요)")
class PipelineIT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connect(dict(SRV)) as c, c.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS slowq_it")
            cur.execute("CREATE DATABASE slowq_it")
        cls.store = connect(dict(SRV, database="slowq_it"))
        apply_schema(cls.store, os.path.join(HERE, "schema.sql"))
        with cls.store.cursor() as cur:
            cur.execute("""INSERT INTO cmdb_cluster (cluster, host, port, realm, tag, owner, owner_team, slack_channel, collect)
                           VALUES ('it-db','127.0.0.1',3307,'test','주문','dev-kim','주문개발팀','#it-alert',1)""")
        cls.target = connect(dict(SRV, database="shop"))

    @classmethod
    def tearDownClass(cls):
        cls.target.close(); cls.store.close()
        with connect(dict(SRV)) as c, c.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS slowq_it")

    def setUp(self):                                     # 테스트마다 저장소를 비우고 CMDB 를 처음 상태로
        with self.store.cursor() as cur:
            for t in ("digest_snapshot", "slow_digest_daily", "tuning_ticket", "ticket_event"):
                cur.execute(f"TRUNCATE TABLE {t}")
            cur.execute("UPDATE cmdb_cluster SET host='127.0.0.1', port=3307, collect=1")

    def test_pipeline(self):
        rules = load(os.path.join(HERE, "config.example.ini"))["rules"]
        rules = dict(rules, min_sec=0.05, min_q=3)            # 테스트 쿼리가 짧게 끝나도 잡히도록
        # ① 기준 스냅숏 → 실행 0건 저장
        self.assertEqual(collect.collect(self.store, self.target, "it-db", "2026-10-01"), 0)
        # ② 느린 쿼리(인덱스 없는 컬럼 조건)를 4번 실행 후 수집
        with self.target.cursor() as cur:
            for _ in range(4):
                cur.execute("SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN7'"); cur.fetchall()
        n = collect.collect(self.store, self.target, "it-db", "2026-10-02")
        self.assertGreaterEqual(n, 1)
        with self.store.cursor() as cur:
            cur.execute("SELECT exec_cnt, avg_sec FROM slow_digest_daily WHERE log_date='2026-10-02' AND query_text LIKE %s",
                        ("%coupon_code%",))
            row = cur.fetchone()
        self.assertEqual(row["exec_cnt"], 4)
        self.assertGreater(row["avg_sec"], 0.05)
        # ③ 검출 → 발행 (CMDB 담당자) → 같은 날 다시 발행해도 0건
        hits = detect.run(self.store, "2026-10-02", rules)
        coupon = [h for h in hits if "coupon_code" in h["query_text"]]
        self.assertTrue(coupon and "기준초과" in coupon[0]["reasons"])
        made = tickets.issue(self.store, "2026-10-02", coupon)
        self.assertEqual(len(made), 1); self.assertEqual(made[0]["owner"], "dev-kim")
        self.assertEqual(tickets.issue(self.store, "2026-10-02", coupon), [])
        # ④ 추적: 다음 날 평균이 기준의 절반 이하 → RESOLVED, 다시 느려지면 → REOPENED
        q = coupon[0]["qhash"]
        with self.store.cursor() as cur:
            for d, avg in (("2026-10-03", 0.0001), ("2026-10-04", coupon[0]["avg_sec"])):
                cur.execute("""INSERT INTO slow_digest_daily (log_date, cluster, qhash, query_text, exec_cnt, total_sec, avg_sec, rows_examined)
                               VALUES (%s,'it-db',%s,'x',4,%s,%s,0)""", (d, q, avg * 4, avg))
        self.assertEqual(tickets.track(self.store, "2026-10-03")[0][2], "RESOLVED")
        self.assertEqual(tickets.track(self.store, "2026-10-04")[0][2], "REOPENED")
        with self.store.cursor() as cur:
            cur.execute("SELECT event FROM ticket_event ORDER BY id")
            self.assertEqual([r["event"] for r in cur.fetchall()], ["CREATED", "RESOLVED", "REOPENED"])

    def test_top_n_counts_only_new_tickets(self):
        """상한(top_n)은 '새로 발행한 것'만 센다 — 이미 티켓이 있는 상위 쿼리가 자리를 차지하면 안 된다."""
        hit = lambda q, t: {"cluster": "it-db", "qhash": q, "query_text": "SELECT ?", "exec_cnt": 9,
                            "avg_sec": 0.3, "total_sec": t, "reasons": ["기준초과"]}
        tickets.issue(self.store, "2026-10-05", [hit("a" * 32, 9)])
        made = tickets.issue(self.store, "2026-10-06", [hit("a" * 32, 9), hit("b" * 32, 5)], top_n=1)
        self.assertEqual(len(made), 1)
        self.assertIn("bbbbbbbb", made[0]["title"])

    def test_store_schema_is_not_collected(self):
        """저장소가 수집 대상과 같은 서버여도, 저장소 자신의 쿼리는 수집하지 않는다."""
        collect.collect(self.store, self.target, "it-db", "2026-10-01", exclude_schema="slowq_it")
        collect.collect(self.store, self.target, "it-db", "2026-10-02", exclude_schema="slowq_it")
        with self.store.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM digest_snapshot WHERE schema_name = 'slowq_it'")
            self.assertEqual(cur.fetchone()["n"], 0)

    def test_cli_daily(self):
        """설정 파일 + 환경 변수 비밀번호로 daily 를 두 번: 첫날은 기준만, 다음 날은 수집 · 검출까지."""
        import io, tempfile
        from slowq import cli
        with open(os.path.join(HERE, "config.example.ini"), encoding="utf-8") as fh:
            ini = fh.read()
        ini = (ini.replace("user = slowq_store", "user = root").replace("database = slowq", "database = slowq_it")
                  .replace("port = 3306", "port = 3307").replace("user = slowq_collector", "user = root"))
        ini = re.sub(r"(?m)^min_sec\s*=\s*[\d.]+", "min_sec = 0.05", ini)   # 예시 설정값이 바뀌어도 테스트 기준은 그대로
        ini = re.sub(r"(?m)^min_q\s*=\s*\d+", "min_q = 3", ini)
        with tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False, encoding="utf-8") as f:
            f.write(ini)
        env = {"SLOWQ_STORE_PASSWORD": SRV["password"], "SLOWQ_TARGET_PASSWORD": SRV["password"]}
        try:
            with mock.patch.dict(os.environ, env):
                out = io.StringIO()
                for day in ("2026-11-01", "2026-11-02", "2026-11-03"):   # 사흘째부터 이력(Decimal)이 생긴다
                    with self.target.cursor() as cur:
                        for _ in range(3):
                            cur.execute("SELECT COUNT(*) FROM orders WHERE coupon_code = 'CPN9'"); cur.fetchall()
                    r = cli.daily(cli.load(f.name), day, out)
                    self.assertEqual(r["failed"], [])
            self.assertIn("수집 it-db", out.getvalue())
            self.assertTrue(any("coupon_code" in (h["query_text"] or "") for h in r["hits"]))
        finally:
            os.unlink(f.name)

    def test_back_to_back_collect_same_second(self):
        """같은 초 안에 두 번 수집해도 스냅숏 키가 겹치지 않는다 (버그 ①)."""
        collect.collect(self.store, self.target, "it-db", "2026-12-01", exclude_schema="slowq_it")
        collect.collect(self.store, self.target, "it-db", "2026-12-01", exclude_schema="slowq_it")
        with self.store.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT snap_at) AS n FROM digest_snapshot")
            self.assertEqual(cur.fetchone()["n"], 2)


if __name__ == "__main__":
    unittest.main()
