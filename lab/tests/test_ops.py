"""운영 반영 · 관리 스크립트의 순수 로직 테스트. lab 에서: .venv/bin/python -m unittest discover -s tests"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ai"))
from apply_fix import build_plan, PlanError, precheck, can_apply, find_duplicate   # noqa: E402
from report import summarize, status_as_of     # noqa: E402
from verify import safe_index_ddl               # noqa: E402

REC = {"proposal": "ALTER TABLE orders ADD INDEX ix_orders_user_ordered (user_id, ordered_at);",
       "verify": {"pass": True, "line": "시간 261.5 ms → 0.15 ms (1785배) · 결과 동일 True"}}


class PlanTest(unittest.TestCase):
    def test_online_ddl_and_rollback(self):
        p = build_plan(REC)
        self.assertEqual(p["apply"], "ALTER TABLE orders ADD INDEX ix_orders_user_ordered (user_id, ordered_at), "
                                     "ALGORITHM=INPLACE, LOCK=NONE")
        self.assertEqual(p["rollback"], "ALTER TABLE orders DROP INDEX ix_orders_user_ordered")
        self.assertEqual((p["table"], p["index"]), ("orders", "ix_orders_user_ordered"))

    def test_refuse_unverified(self):                      # 실측 검증을 통과하지 못한 제안은 계획을 만들지 않는다
        with self.assertRaises(PlanError):
            build_plan(dict(REC, verify={"pass": False}))
        with self.assertRaises(PlanError):
            build_plan(dict(REC, verify=None))

    def test_no_analysis_message(self):                    # 분석이 없는 티켓은 '탈락'이 아니라 '분석 전'으로 알린다
        with self.assertRaisesRegex(PlanError, "분석 · 검증 결과가 없습니다"):
            build_plan(None)

    def test_precheck_blocks_long_transactions(self):    # 메타데이터 락: 오래 열린 트랜잭션이 있으면 반영하지 않는다
        self.assertEqual(precheck(long_trx=0)["ok"], True)
        r = precheck(long_trx=2)
        self.assertFalse(r["ok"]); self.assertIn("트랜잭션", r["reason"])

    def test_can_apply_only_open_tickets(self):            # 이미 해결된 티켓에 다시 반영하지 않는다
        self.assertTrue(can_apply("REOPENED")); self.assertTrue(can_apply("OPEN"))
        self.assertFalse(can_apply("RESOLVED"))

    def test_find_duplicate_with_uppercase_keys(self):    # MySQL 8.0 information_schema 는 열 이름을 대문자로 돌려준다
        rows = [{"INDEX_NAME": "PRIMARY", "COLS": "order_id"}, {"INDEX_NAME": "ix_other", "COLS": "user_id,ordered_at"}]
        self.assertEqual(find_duplicate(rows, "ix_orders_user_ordered", "user_id,ordered_at"), "ix_other")
        self.assertIsNone(find_duplicate(rows[:1], "ix_orders_user_ordered", "user_id,ordered_at"))
        self.assertEqual(find_duplicate([{"index_name": "ix_a", "cols": "c"}], "ix_a", "z"), "ix_a")   # 소문자 키도

    def test_refuse_non_index_ddl(self):                   # 되돌리기가 분명하지 않은 변경은 자동 계획 대상이 아니다
        with self.assertRaises(PlanError):
            build_plan(dict(REC, proposal="1) 인덱스 추가 2) keyset 으로 쿼리 변경"))


D = dt.date


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tickets = [
            {"ticket_id": 1, "owner_team": "주문개발팀", "status": "RESOLVED", "baseline_avg_sec": 0.27,
             "created_at": dt.datetime(2026, 9, 29, 9), "cluster": "a", "qhash": "q1"},
            {"ticket_id": 2, "owner_team": "정산개발팀", "status": "OPEN", "baseline_avg_sec": 0.28,
             "created_at": dt.datetime(2026, 9, 29, 9), "cluster": "b", "qhash": "q1"},
            {"ticket_id": 3, "owner_team": "주문개발팀", "status": "OPEN", "baseline_avg_sec": 0.5,
             "created_at": dt.datetime(2026, 10, 12, 9), "cluster": "a", "qhash": "q2"}]
        self.events = [{"ticket_id": 1, "at": dt.datetime(2026, 10, 10, 9), "event": "REOPENED"},
                       {"ticket_id": 1, "at": dt.datetime(2026, 10, 13, 9), "event": "RESOLVED"},
                       {"ticket_id": 3, "at": dt.datetime(2026, 10, 12, 9), "event": "CREATED"}]
        self.daily = [{"cluster": "a", "qhash": "q1", "log_date": D(2026, 10, 13), "avg_sec": 0.0001, "exec_cnt": 40},
                      {"cluster": "a", "qhash": "q1", "log_date": D(2026, 10, 12), "avg_sec": 0.27, "exec_cnt": 44},
                      {"cluster": "b", "qhash": "q1", "log_date": D(2026, 10, 13), "avg_sec": 0.28, "exec_cnt": 20},
                      {"cluster": "a", "qhash": "q2", "log_date": D(2026, 10, 13), "avg_sec": 0.5, "exec_cnt": 6}]

    def test_kpis(self):
        r = summarize(self.tickets, self.events, self.daily, end=D(2026, 10, 13), days=7)
        self.assertEqual(r["new"], 1)                      # 기간 안에 만든 티켓 (#3)
        self.assertEqual(r["resolved"], 1)
        self.assertEqual(r["reopened"], 1)
        self.assertEqual(r["open"], 2)
        self.assertEqual(r["open_age_days"], {2: 14, 3: 1})
        self.assertEqual(r["saved_sec"], round((0.27 - 0.0001) * 40, 1))   # 해결 기준을 만족한 날만 · 소수 첫째 자리
        self.assertEqual(r["open_by_team"], {"정산개발팀": 1, "주문개발팀": 1})

    def test_status_as_of_past_date(self):            # 지난 날짜 리포트는 그날의 상태로 (지금 상태가 아니라)
        ev = [{"ticket_id": 1, "at": dt.datetime(2026, 9, 29, 9), "event": "CREATED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 7, 9), "event": "RESOLVED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 10, 9), "event": "REOPENED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 12, 9), "event": "AI_ANALYZED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 13, 8), "event": "APPLIED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 13, 9), "event": "RESOLVED"}]
        self.assertEqual(status_as_of(ev, D(2026, 10, 12)), "REOPENED")
        self.assertEqual(status_as_of(ev, D(2026, 10, 13)), "RESOLVED")
        self.assertEqual(status_as_of(ev, D(2026, 10, 8)), "RESOLVED")
        self.assertIsNone(status_as_of(ev, D(2026, 9, 28)))          # 경계: 발행 전이면 집계 대상 아님

    def test_report_uses_status_as_of(self):
        t = [dict(self.tickets[0], status="RESOLVED")]
        ev = [{"ticket_id": 1, "at": dt.datetime(2026, 9, 29, 9), "event": "CREATED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 10, 9), "event": "REOPENED"},
              {"ticket_id": 1, "at": dt.datetime(2026, 10, 13, 9), "event": "RESOLVED"}]
        self.assertEqual(summarize(t, ev, [], end=D(2026, 10, 12))["open"], 1)
        self.assertEqual(summarize(t, ev, [], end=D(2026, 10, 13))["open"], 0)

    def test_resolved_counts_tickets_not_events(self):     # 같은 티켓이 기간 안에 두 번 해결돼도 1건
        ev = self.events + [{"ticket_id": 1, "at": dt.datetime(2026, 10, 8, 9), "event": "RESOLVED"}]
        self.assertEqual(summarize(self.tickets, ev, self.daily, end=D(2026, 10, 13))["resolved"], 1)

    def test_period_boundary(self):                        # 경계: 기간 밖(8일 전) 이벤트는 세지 않는다
        r = summarize(self.tickets, self.events, self.daily, end=D(2026, 10, 18), days=7)
        self.assertEqual(r["reopened"], 0)

    def test_empty(self):                                  # 실패 방지: 데이터가 없어도 0 으로
        r = summarize([], [], [], end=D(2026, 10, 13))
        self.assertEqual((r["new"], r["open"], r["saved_sec"]), (0, 0, 0))


class VerifyDdlTest(unittest.TestCase):
    def test_single_add_index(self):                       # 26강 verify: 한 절짜리 ADD INDEX 만, 테이블까지 읽어 되돌린다
        self.assertEqual(safe_index_ddl("ALTER TABLE users ADD INDEX ix_email (email)"),
                         ("users", "ix_email", "ALTER TABLE users ADD INDEX ix_email (email)"))

    def test_rejects_extra_clauses(self):                  # 다른 절이 붙으면 되돌릴 수 없으므로 실행하지 않는다
        self.assertIsNone(safe_index_ddl("ALTER TABLE orders ADD INDEX ix_a (c), DROP COLUMN z"))
        self.assertIsNone(safe_index_ddl("ALTER TABLE orders ADD (c INT)"))


if __name__ == "__main__":
    unittest.main()


class SimulateCliTest(unittest.TestCase):
    """simulate.py --help 는 도움말만 보여 주고 DB 에 쓰지 않는다 (31차 검증: --help 가 14일 재현을 실행해 버렸다)"""

    def _run(self, argv):
        import contextlib, io, runpy, types
        from unittest import mock
        touched = []
        stub = lambda name: types.SimpleNamespace(main=lambda *a, **k: touched.append(name), run=lambda *a, **k: touched.append(name),
                                                   issue=lambda *a, **k: touched.append(name), track=lambda *a, **k: touched.append(name),
                                                   connect=lambda *a, **k: touched.append(name) or mock.MagicMock())
        mods = {m: stub(m) for m in ("collector", "tickets", "workload", "common")}
        path = os.path.join(os.path.dirname(__file__), "..", "scripts", "simulate.py")
        out = io.StringIO()
        with mock.patch.dict(sys.modules, mods), mock.patch.object(sys, "argv", ["simulate.py"] + argv), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                runpy.run_path(path, run_name="__main__")
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), touched

    def test_help_does_not_touch_db(self):
        code, out, touched = self._run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage", out)
        self.assertEqual(touched, [])

    def test_unknown_arg_refused(self):
        code, _, touched = self._run(["--bogus"])
        self.assertEqual(code, 2)
        self.assertEqual(touched, [])

    def test_no_args_runs(self):                             # 인자 없이 실행하면 예전처럼 재현을 돈다
        _, _, touched = self._run([])
        self.assertIn("collector", touched)
