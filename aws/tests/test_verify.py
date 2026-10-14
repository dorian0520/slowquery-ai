"""Verify: 검증 DB 에 ADD INDEX 한 절만 만들고, 무슨 일이 있어도 되돌린다."""
import pytest

from slowq_aws import guards
from slowq_aws import verify as V

DDL = "ALTER TABLE orders ADD INDEX ix_u (user_id, ordered_at)"
TEST = "SELECT order_id FROM orders WHERE user_id = 1001"


def verify_db(fake_conn, fail_after_add=False, exists_before=False):
    """인덱스 존재 여부를 기억하는 가짜 검증 DB. fail_after_add 면 인덱스를 만든 뒤 측정 쿼리가 실패한다."""
    state = {"exists": exists_before, "added": False}

    def stats(sql, args):
        return [{"n": 1 if state["exists"] else 0}]

    def on_add():
        state["exists"] = state["added"] = True

    def on_drop():
        state["exists"] = False

    def select_fail():
        return RuntimeError("측정 실패") if (fail_after_add and state["added"]) else None

    conn = fake_conn(rules=[(r"information_schema\.statistics", stats), (r"^SELECT order_id", [{"order_id": 1}])],
                     fail=[(r"ADD INDEX", lambda: on_add()), (r"DROP INDEX", lambda: on_drop()),
                           (r"^SELECT order_id", select_fail)])
    return conn, state


def test_pass_and_rolled_back(fake_conn):
    conn, state = verify_db(fake_conn)
    r = V.run(conn, DDL, TEST)
    assert "same" in r and r["same"] is True
    assert any("ADD INDEX ix_u" in s for s in conn.sqls()) and any("DROP INDEX ix_u" in s for s in conn.sqls())
    assert state["exists"] is False and r["rolled_back_by_guard"] is False


def test_exception_during_measure_still_rolls_back(fake_conn):
    conn, state = verify_db(fake_conn, fail_after_add=True)
    with pytest.raises(RuntimeError, match="측정 실패"):
        V.run(conn, DDL, TEST)
    assert state["exists"] is False                              # 예외가 나도 인덱스는 남지 않는다
    assert any("DROP INDEX ix_u" in s for s in conn.sqls())


def test_extra_clause_is_not_executed(fake_conn):
    conn, _ = verify_db(fake_conn)
    r = V.run(conn, DDL + ", ADD COLUMN z INT", TEST)
    assert "skipped" in r and not any(s.startswith("ALTER") for s in conn.sqls())


def test_existing_index_name_is_not_touched(fake_conn):
    conn, state = verify_db(fake_conn, exists_before=True)
    r = V.run(conn, DDL, TEST)
    assert "skipped" in r and state["exists"] is True
    assert not any(s.startswith("ALTER") for s in conn.sqls())


def test_non_select_test_sql_rejected(fake_conn):
    conn, _ = verify_db(fake_conn)
    with pytest.raises(guards.UnsafeSQL):
        V.run(conn, DDL, "DELETE FROM orders")
    assert not any(s.startswith("ALTER") for s in conn.sqls())


def test_handler_skips_when_analysis_not_ok():
    r = V.handler({"analysis": {"ticket_id": 3, "status": "FORMAT_ERROR"}, "ticket": {"ticket_id": 3}}, None)
    assert r == {"ticket_id": 3, "status": "SKIPPED", "reason": "분석 결과 FORMAT_ERROR"}


def test_handler_skips_rewrite_only_proposal():
    a = {"ticket_id": 3, "status": "OK", "proposal": {"proposal": "keyset 페이지네이션으로 재작성", "test_sql": TEST}}
    assert V.handler({"analysis": a}, None)["status"] == "SKIPPED"


def test_rollback_confirmation_failure_never_returns_pass(fake_conn, monkeypatch):
    conn, state = verify_db(fake_conn)
    def cannot_confirm(*args, **kwargs):
        raise RuntimeError("인덱스 상태 조회 불가")
    monkeypatch.setattr(V, "ensure_rolled_back", cannot_confirm)
    with pytest.raises(RuntimeError, match="되돌리기 확인 실패"):
        V.run(conn, DDL, TEST)
