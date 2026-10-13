"""순수 로직 단위 테스트 (DB 없이). python3 -m unittest discover -s tests"""
import datetime as dt
import unittest

from slowq.collect import delta_rows
from slowq.detect import detect
from slowq.mask import mask
from slowq.tickets import next_status
from slowq.analyze import parse_proposals, ProposalFormatError, claude_cmd

PS = 1e12


def snap(digest, cnt, sum_s, rows=0, first="2026-10-01 00:00:00", text="SELECT ?", schema="shop"):
    return {"digest": digest, "schema_name": schema, "digest_text": text, "count_star": cnt,
            "sum_timer_wait": int(sum_s * PS), "sum_rows_examined": rows, "first_seen": first}


class DeltaTest(unittest.TestCase):
    def test_normal_delta(self):
        prev = {("shop", "a"): snap("a", 100, 10.0, 1000)}
        cur = [snap("a", 150, 17.5, 1600)]
        r = delta_rows(prev, cur)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["exec_cnt"], 50)
        self.assertAlmostEqual(r[0]["total_sec"], 7.5)
        self.assertAlmostEqual(r[0]["avg_sec"], 0.15)
        self.assertEqual(r[0]["rows_examined"], 600)

    def test_new_digest_counts_all(self):          # 직전 스냅숏에 없던 지문 = 전부 오늘 실행분
        r = delta_rows({}, [snap("b", 3, 0.9)])
        self.assertEqual(r[0]["exec_cnt"], 3)

    def test_no_change_is_skipped(self):           # 경계: 실행이 없으면 행을 만들지 않는다
        prev = {("shop", "a"): snap("a", 100, 10.0)}
        self.assertEqual(delta_rows(prev, [snap("a", 100, 10.0)]), [])

    def test_restart_detected_by_first_seen(self):  # 재시작: 누적값이 직전보다 커도 FIRST_SEEN 이 바뀌면 리셋으로 본다
        prev = {("shop", "a"): snap("a", 100, 10.0, first="2026-10-01 00:00:00")}
        cur = [snap("a", 120, 12.0, first="2026-10-12 08:00:00")]
        r = delta_rows(prev, cur)
        self.assertEqual(r[0]["exec_cnt"], 120)

    def test_counter_decrease_treated_as_reset(self):  # 실패 방지: 음수 차이를 만들지 않는다
        prev = {("shop", "a"): snap("a", 100, 10.0)}
        r = delta_rows(prev, [snap("a", 30, 3.0)])
        self.assertEqual(r[0]["exec_cnt"], 30)
        self.assertGreaterEqual(r[0]["total_sec"], 0)


    def test_same_digest_in_two_schemas(self):     # 같은 지문이 스키마별로 따로 집계된다
        prev = {("shop", "a"): snap("a", 100, 10.0), ("shop2", "a"): snap("a", 5, 1.0, schema="shop2")}
        cur = [snap("a", 110, 11.0), snap("a", 7, 1.4, schema="shop2")]
        self.assertEqual(sorted(r["exec_cnt"] for r in delta_rows(prev, cur)), [2, 10])


class DetectTest(unittest.TestCase):
    RULES = {"min_sec": 0.2, "min_q": 5, "worse_ratio": 2.0, "spike_ratio": 2.0, "spike_min_total": 1.0}

    def row(self, q, cnt, avg):
        return {"cluster": "c1", "qhash": q, "query_text": "SELECT ?", "exec_cnt": cnt, "avg_sec": avg,
                "total_sec": cnt * avg}

    def test_over_threshold(self):
        hits = detect([self.row("q1", 10, 0.3)], history={}, rules=self.RULES)
        self.assertEqual(hits[0]["reasons"], ["기준초과"])

    def test_boundary_min_q_not_met(self):          # 경계: 횟수 미달이면 기준초과 아님
        self.assertEqual(detect([self.row("q1", 4, 0.9)], history={}, rules=self.RULES), [])

    def test_worse_vs_previous_day(self):
        hist = {("c1", "q1"): {"prev_avg": 0.0001, "avg_cnt": 10}}
        hits = detect([self.row("q1", 10, 0.27)], history=hist, rules=self.RULES)
        self.assertIn("악화", hits[0]["reasons"])

    def test_spike(self):
        hist = {("c1", "q2"): {"prev_avg": 0.17, "avg_cnt": 16}}
        hits = detect([self.row("q2", 61, 0.17)], history=hist, rules=self.RULES)
        self.assertEqual(hits[0]["reasons"], ["급증"])

    def test_new_query(self):
        hits = detect([self.row("q3", 6, 0.25)], history={}, rules=self.RULES, known={("c1", "older")})
        self.assertIn("신규", hits[0]["reasons"])

    def test_ddl_is_not_new(self):                  # 실패 케이스: DDL 은 신규로 잡지 않는다
        r = self.row("q4", 6, 0.01); r["query_text"] = "ALTER TABLE `orders` ADD INDEX ..."
        self.assertEqual(detect([r], history={}, rules=self.RULES, known=set()), [])


class MaskTest(unittest.TestCase):
    def test_strings_numbers_hex(self):
        self.assertEqual(mask("SELECT * FROM t1 WHERE email = 'a@b.com' AND id = 42 AND h = 0x1F"),
                         "SELECT * FROM t1 WHERE email = '?' AND id = ? AND h = ?")

    def test_identifier_digits_kept(self):          # 경계: 이름 속 숫자는 지우지 않는다
        self.assertEqual(mask("SELECT col2 FROM `t2`"), "SELECT col2 FROM `t2`")


class TicketStateTest(unittest.TestCase):
    def test_resolve_when_half(self):
        self.assertEqual(next_status("OPEN", base=0.27, now=0.0001), "RESOLVED")

    def test_stay_open_above_half(self):            # 경계: 정확히 절반 초과면 그대로
        self.assertEqual(next_status("OPEN", base=0.30, now=0.16), "OPEN")

    def test_reopen_when_back(self):
        self.assertEqual(next_status("RESOLVED", base=0.27, now=0.27), "REOPENED")

    def test_hysteresis_no_flap(self):              # 해결과 재발 사이 간격: 0.5~0.8 구간은 상태 유지
        self.assertEqual(next_status("RESOLVED", base=0.30, now=0.20), "RESOLVED")

    def test_no_data_keeps_status(self):            # 실패 방지: 데이터 없음은 판단 보류
        self.assertEqual(next_status("OPEN", base=0.3, now=None), "OPEN")


class ParseTest(unittest.TestCase):
    def test_parse_fenced_json(self):
        p = parse_proposals('설명\n```json\n[{"qhash": "a", "proposal": "ALTER TABLE t ADD INDEX ix (c)"}]\n```')
        self.assertEqual(p[0]["qhash"], "a")

    def test_broken_json_raises(self):              # 실습에서 실제로 만난 실패: 괄호를 잘못 닫음
        with self.assertRaises(ProposalFormatError):
            parse_proposals('[{"qhash": "a", "proposal": "x"]')

    def test_missing_keys_raises(self):
        with self.assertRaises(ProposalFormatError):
            parse_proposals('[{"qhash": "a"}]')



from decimal import Decimal
from slowq.verify import index_target, judge, result_digest
from slowq.tickets import issuable
from slowq.publish import DryRunPublisher


class VerifyTest(unittest.TestCase):
    def test_index_target(self):
        self.assertEqual(index_target("ALTER TABLE orders ADD INDEX ix_a (user_id, ordered_at);")[:2], ("orders", "ix_a"))
        self.assertEqual(index_target("alter table `shop`.`orders` add key ix_b (c)")[:2], ("`shop`.`orders`", "ix_b"))

    def test_index_target_rejects_unknown(self):     # 되돌릴 수 없는 DDL 은 실행하지 않는다
        self.assertIsNone(index_target("ALTER TABLE orders ADD (c INT)"))
        self.assertIsNone(index_target("DROP TABLE orders"))

    def test_judge(self):
        self.assertTrue(judge(0.26, 0.0002, same=True))
        self.assertFalse(judge(0.51, 0.50, same=True))       # 경계: 절반 넘게 남으면 탈락
        self.assertFalse(judge(0.26, 0.0002, same=False))    # 빨라도 결과가 다르면 탈락


class PublishTest(unittest.TestCase):
    def test_dry_run_records_without_sending(self):
        p = DryRunPublisher()
        p.publish({"title": "t", "channel": "#c", "owner": "o", "ticket_id": 1})
        self.assertEqual(p.sent[0]["channel"], "#c")


class RegressionTest(unittest.TestCase):
    RULES = DetectTest.RULES

    def row(self, q, cnt, avg, text="SELECT ?", cluster="c1"):
        return {"cluster": cluster, "qhash": q, "query_text": text, "exec_cnt": cnt, "avg_sec": avg, "total_sec": cnt * avg}

    def test_decimal_history_from_mysql(self):          # MySQL AVG() 는 Decimal — 사흘째부터 죽던 버그
        hist = {("c1", "q2"): {"prev_avg": Decimal("0.17"), "avg_cnt": Decimal("16.0000")}}
        self.assertEqual(detect([self.row("q2", 61, 0.17)], history=hist, rules=self.RULES)[0]["reasons"], ["급증"])

    def test_non_business_statements_excluded_everywhere(self):   # DDL · SET · SHOW 는 어떤 규칙에도 걸리지 않는다
        rows = [self.row("q5", 50, 0.9, "SET NAMES ?"), self.row("q6", 50, 0.9, "ALTER TABLE `t` ADD INDEX ...")]
        self.assertEqual(detect(rows, history={}, rules=self.RULES, known=set()), [])

    def test_new_only_for_clusters_with_history(self):  # 새로 추가한 클러스터의 첫날 지문은 '신규'로 쏟아내지 않는다
        known = {("c1", "old")}
        hits = detect([self.row("x", 6, 0.01, cluster="c2"), self.row("y", 6, 0.01, cluster="c1")],
                      history={}, rules=self.RULES, known=known)
        self.assertEqual([(h["cluster"], h["reasons"]) for h in hits], [("c1", ["신규"])])

    def test_issuable_only_over_threshold(self):        # 발행은 기준초과(악화 포함)만 — 신규 · 급증은 검출 목록에만
        self.assertTrue(issuable({"reasons": ["기준초과", "악화"]}))
        self.assertFalse(issuable({"reasons": ["신규"]}))
        self.assertFalse(issuable({"reasons": ["급증"]}))

    def test_index_target_rejects_extra_clauses(self):  # 되돌리지 못하는 절이 붙은 DDL 은 검증하지 않는다
        self.assertIsNone(index_target("ALTER TABLE orders ADD INDEX ix_a (c), ADD COLUMN z INT"))
        self.assertIsNone(index_target("ALTER TABLE orders ADD INDEX ix_a (c), DROP INDEX ix_old"))
        self.assertEqual(index_target("ALTER TABLE orders ADD INDEX ix_a (c1, c2);")[:2], ("orders", "ix_a"))

    def test_result_digest_ignores_row_order(self):     # 인덱스가 생겨 행 순서만 바뀐 것은 같은 결과
        self.assertEqual(result_digest([(1, "a"), (2, "b")]), result_digest([(2, "b"), (1, "a")]))
        self.assertNotEqual(result_digest([(1, "a")]), result_digest([(1, "b")]))

    def test_claude_cmd_disables_builtin_tools(self):   # --allowedTools 는 화이트리스트가 아니다 → 기본 도구는 --tools "" 로 끈다
        cmd = claude_cmd("분석", "mcp.json", ("mcp__labdb__explain",))
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "mcp__labdb__explain")

    def test_parse_checks_types(self):
        with self.assertRaises(ProposalFormatError):
            parse_proposals('[{"qhash": 1, "proposal": null}]')


if __name__ == "__main__":
    unittest.main()
