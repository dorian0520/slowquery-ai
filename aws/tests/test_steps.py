"""나머지 단계: 수집 격리 · 검출 압축 · 첨부 · 리포트 · 변경 계획 · 초기화 권한 · 부하."""
import datetime as dt
import json

import pytest

from slowq_aws import apply_plan, attach, collect, common, detect, init_db, report, workload


def test_resolve_log_date():
    assert common.resolve_log_date({"log_date": "2026-10-12"}) == "2026-10-12"
    assert common.resolve_log_date({}) == (common.today_local() - dt.timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        common.resolve_log_date({"log_date": "12/10/2026"})


def test_is_weekly():
    assert collect.is_weekly("2026-10-11", 6) is True          # 일요일
    assert collect.is_weekly("2026-10-12", 6) is False


def test_collect_isolates_cluster_failure(fake_conn, monkeypatch):
    store = fake_conn(rules=[(r"FROM cmdb_cluster", [{"cluster": "a", "host": "h1", "port": 3306},
                                                      {"cluster": "b", "host": "h2", "port": 3306}])])
    monkeypatch.setattr(collect.scollect, "collect", lambda st, c, cl, d, exclude_schema="": 5)

    def connect_target(h, p):
        if h == "h1":
            raise OSError("접속 실패")
        return fake_conn()
    got, failed = collect.run(store, connect_target, "2026-10-12")
    assert got == {"b": 5} and failed == ["a"]


def test_detect_compact_limits_size():
    hits = [{"cluster": "c", "qhash": str(i), "exec_cnt": 1, "total_sec": 1.0, "avg_sec": 1.0, "reasons": ["기준초과"],
             "query_text": "x" * 5000, "rows_examined": 1} for i in range(300)]
    out = detect.compact(hits)
    assert len(out) == detect.MAX_HITS and len(out[0]["query_text"]) == detect.TEXT_LIMIT and "rows_examined" not in out[0]


def test_attach_records_format_error_for_human_review(fake_conn):
    s = fake_conn()
    note = attach.attach(s, 3, "2026-10-12", {"status": "FORMAT_ERROR", "error": "JSON 배열이 아닙니다"}, None)
    assert "사람 검토" in note
    upd = [a for q, a in s.executed if q.startswith("UPDATE tuning_ticket")][0]
    assert json.loads(upd[0])["status"] == "FORMAT_ERROR" and upd[1] == 0


def test_attach_ok_with_pass(fake_conn):
    s = fake_conn()
    a = {"status": "OK", "proposal": {"cause": "c", "evidence": ["e"], "proposal": "ALTER TABLE t ADD INDEX i (c)",
                                      "confidence": "high", "test_sql": "SELECT 1"}}
    note = attach.attach(s, 3, "2026-10-12", a, {"status": "PASS", "ddl": "ALTER TABLE t ADD INDEX i (c)",
                                                  "before_sec": 0.3, "after_sec": 0.001, "same": True})
    upd = [a for q, a in s.executed if q.startswith("UPDATE tuning_ticket")][0]
    assert "실측 통과" in note and upd[1] == 1 and json.loads(upd[0])["verify"]["pass"] is True


def T(tid, created, status="OPEN", base=0.3, team="t1"):
    return {"ticket_id": tid, "cluster": "c", "qhash": f"q{tid}", "status": status, "baseline_avg_sec": base,
            "owner_team": team, "created_at": dt.datetime.fromisoformat(created)}


def test_report_summarize_and_render():
    end = dt.date(2026, 10, 13)
    tickets = [T(1, "2026-10-08 09:00:00"), T(2, "2026-10-01 09:00:00", status="RESOLVED")]
    events = [{"ticket_id": 2, "at": dt.datetime(2026, 10, 1, 9), "event": "CREATED"},
              {"ticket_id": 2, "at": dt.datetime(2026, 10, 10, 9), "event": "RESOLVED"}]
    daily = [{"cluster": "c", "qhash": "q2", "log_date": dt.date(2026, 10, 11), "avg_sec": 0.001, "exec_cnt": 100}]
    r = report.summarize(tickets, events, daily, end)
    assert (r["new"], r["resolved"], r["open"]) == (1, 1, 1)
    assert r["saved_sec"] == round((0.3 - 0.001) * 100, 1)
    md = report.to_markdown(r, tickets)
    assert md.startswith("# 슬로우 쿼리 주간 리포트") and "#1 c q1" in md
    assert "<h1>" in report.to_html(md) and "<script" not in report.to_html(md + "\n<script>")


def test_report_handler_writes_s3(fake_conn, monkeypatch):
    monkeypatch.setenv("REPORT_BUCKET", "bucket-x")
    monkeypatch.setattr(common, "store_conn", lambda: fake_conn())
    puts = []

    class S3:
        def put_object(self, **kw):
            puts.append(kw)
    out = report.handler({"log_date": "2026-10-11"}, None, s3=S3())
    assert [p["Key"] for p in puts] == ["reports/2026-10-11/weekly.md", "reports/2026-10-11/weekly.html"]
    assert out["objects"]["md"] == "s3://bucket-x/reports/2026-10-11/weekly.md"


def ticket(rec, status="OPEN"):
    return {"ticket_id": 1, "status": status, "title": "t", "cluster": "shop-db", "recommendation": json.dumps(rec)}


GOOD_REC = {"status": "OK", "test_sql": "SELECT 1",
            "verify": {"pass": True, "ddl": "ALTER TABLE orders ADD INDEX ix_u (user_id, ordered_at)",
                       "before_sec": 0.3, "after_sec": 0.001, "same": True}}


def test_apply_plan_builds_online_ddl_only_for_verified():
    p = apply_plan.build_plan(ticket(GOOD_REC))
    assert p["apply"] == "ALTER TABLE orders ADD INDEX ix_u (user_id, ordered_at), ALGORITHM=INPLACE, LOCK=NONE"
    assert p["rollback"] == "ALTER TABLE orders DROP INDEX ix_u"


@pytest.mark.parametrize("rec,status", [
    (dict(GOOD_REC, verify={"pass": False}), "OPEN"),
    ({"status": "FORMAT_ERROR"}, "OPEN"),
    (GOOD_REC, "RESOLVED"),
    (dict(GOOD_REC, verify=dict(GOOD_REC["verify"], ddl="ALTER TABLE orders ADD INDEX i (c), DROP INDEX j")), "OPEN"),
])
def test_apply_plan_refuses(rec, status):
    with pytest.raises(apply_plan.PlanError):
        apply_plan.build_plan(ticket(rec, status))


def test_apply_plan_never_executes_ddl(fake_conn, monkeypatch):
    monkeypatch.setenv("REPORT_BUCKET", "b")
    monkeypatch.setenv("TARGET_HOST", "h")
    monkeypatch.setenv("AI_SECRET_ARN", "x")
    st = fake_conn(rules=[(r"FROM tuning_ticket WHERE ticket_id", [ticket(GOOD_REC)])])
    ro = fake_conn(rules=[(r"information_schema\.statistics", [{"INDEX_NAME": "PRIMARY", "COLS": "order_id"}])])
    monkeypatch.setattr(common, "store_conn", lambda: st)
    monkeypatch.setattr(common, "connect", lambda *a, **k: ro)
    body = {}

    class S3:
        def put_object(self, **kw):
            body.update(kw)
    out = apply_plan.handler({"ticket_id": 1}, None, s3=S3())
    assert out["executed"] is False and out["duplicate"] is None
    assert not any(q.lstrip().upper().startswith("ALTER") for q in st.sqls() + ro.sqls())
    assert b"ALGORITHM=INPLACE" in body["Body"]


def test_apply_plan_detects_duplicate_columns():
    rows = [{"INDEX_NAME": "ix_old", "COLS": "user_id,ordered_at"}]
    assert apply_plan.find_duplicate(rows, "ix_u", "user_id, ordered_at") == "ix_old"


def test_init_accounts_are_least_privilege():
    acc = init_db.accounts("dba", "shop")
    grants = " ".join(g for _, _, gs in acc for g in gs).upper()
    assert "ALL PRIVILEGES" not in grants and "*.*" not in grants and "WITH GRANT OPTION" not in grants
    verify = [gs for env, where, gs in acc if env == "VERIFY_SECRET_ARN"][0]
    assert all(where == "verify" for env, where, _ in acc if env == "VERIFY_SECRET_ARN")
    assert "ALTER" in verify[0] and "`shop`.*" in verify[0]
    assert not any("ALTER" in g for env, _, gs in acc if env != "VERIFY_SECRET_ARN" for g in gs)


def test_init_password_is_bound_parameter_not_in_sql(fake_conn):
    c = fake_conn()
    with c.cursor() as cur:
        init_db.ensure_user(cur, "slowq_ai", "P@ss-word-xyz", ["GRANT SELECT ON `shop`.* TO {u}"])
    assert not any("P@ss-word-xyz" in s for s in c.sqls())
    assert ("slowq_ai", "P@ss-word-xyz") in [a for _, a in c.executed]


def test_init_partial_sample_requires_explicit_reset(fake_conn):
    c = fake_conn(rules=[(r"information_schema\.schemata", [{"n": 1}]), (r"information_schema\.tables", [{"n": 0}])])
    with pytest.raises(init_db.InitError):
        init_db.load_sample(c, "shop", reset=False)
    assert not any("DROP DATABASE" in s for s in c.sqls())


def test_init_skips_ready_sample(fake_conn):
    c = fake_conn(rules=[(r"information_schema\.schemata", [{"n": 1}]), (r"information_schema\.tables", [{"n": 1}]),
                         (r"COUNT\(\*\) AS n FROM `shop`\.orders", [{"n": 2_000_000}])])
    assert init_db.load_sample(c, "shop").startswith("skip")


def test_workload_stops_before_timeout(fake_conn):
    left = iter([10 ** 6] * 5 + [0] * 1000)
    out = workload.run(fake_conn(), scale=1.0, time_left=lambda: next(left))
    assert out.get("stopped_early") is True and sum(v for k, v in out.items() if k != "stopped_early") == 5
