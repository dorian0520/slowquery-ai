"""Verify 단계: AI 제안 인덱스를 검증 DB(order-db)에만 만들어 전후를 재고, 반드시 되돌린다.

- 실행하는 DDL 은 ADD INDEX 한 절뿐이다 (slowq.verify.index_target 이 다시 만든 문장만 실행).
- test_sql 은 SELECT 한 문장만 허용한다.
- 측정 중 무엇이 실패해도, 끝에서 인덱스가 남아 있는지 다시 확인하고 남았으면 지운다.
- 운영(대상) DB 에는 접속하지 않는다. 검증 계정은 검증 DB 의 서비스 스키마에만 권한이 있다.
"""
from slowq import verify as sverify

from . import common, guards


def _split_table(table):
    parts = [p.strip("`") for p in table.split(".")]
    return (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])


def index_exists(conn, table, index, default_schema):
    schema, name = _split_table(table)
    with conn.cursor() as cur:
        cur.execute("""SELECT COUNT(*) AS n FROM information_schema.statistics
                       WHERE table_schema=%s AND table_name=%s AND index_name=%s""",
                    (schema or default_schema, name, index))
        return bool(cur.fetchone()["n"])


def ensure_rolled_back(conn, table, index, default_schema):
    """검증이 만든 인덱스가 남아 있으면 지운다. 지웠으면 True (= 정상 경로에서 되돌리지 못했다는 뜻이므로 경고)."""
    if index_exists(conn, table, index, default_schema):
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} DROP INDEX {index}")
        return True
    return False


def run(conn, ddl, test_sql, default_schema="shop", max_exec_ms=60000):
    """검증 한 건. 반환: slowq.verify.verify 결과 + rolled_back_by_guard."""
    target = sverify.index_target(ddl)
    if not target:
        return {"pass": False, "skipped": f"되돌릴 수 없는 DDL 이라 검증하지 않음: {(ddl or '')[:80]}"}
    test_sql = guards.select_only(test_sql)
    table, index, _ = target
    if index_exists(conn, table, index, default_schema):     # 원래 있던 인덱스를 검증 끝에 지우지 않도록, 이름이 겹치면 시작하지 않는다
        return {"pass": False, "skipped": f"검증 DB 에 같은 이름의 인덱스가 이미 있음: {index}"}
    with conn.cursor() as cur:
        cur.execute("SET SESSION max_execution_time = %s", (int(max_exec_ms),))   # 너무 느린 테스트 쿼리는 끊는다
    result = None
    try:
        result = sverify.verify(conn, ddl, test_sql)
    finally:
        try:
            dropped = ensure_rolled_back(conn, table, index, default_schema)
        except Exception as exc:  # noqa: BLE001 — 되돌리기를 확인하지 못하면 통과를 반환하지 않는다
            common.log.exception("검증 DB 인덱스 되돌리기 확인 실패: %s.%s", table, index)
            raise RuntimeError("검증 DB 인덱스 되돌리기 확인 실패 — 사람의 확인 필요") from exc
        if dropped:
            common.log.error("검증 DB 에 인덱스가 남아 있어 지웠습니다: %s.%s", table, index)
    result["rolled_back_by_guard"] = bool(dropped)
    return result


def handler(event, context):
    a = event.get("analysis") or {}
    base = {"ticket_id": a.get("ticket_id") or (event.get("ticket") or {}).get("ticket_id")}
    if a.get("status") != "OK":
        return dict(base, status="SKIPPED", reason=f"분석 결과 {a.get('status')}")
    p = a["proposal"]
    ddl = guards.first_ddl(p.get("proposal"))
    if not ddl:
        return dict(base, status="SKIPPED", reason="ALTER TABLE 제안이 없음 (쿼리 재작성 등 → 사람 검토)")
    try:
        guards.select_only(p.get("test_sql"))
    except guards.UnsafeSQL as e:
        return dict(base, status="SKIPPED", reason=f"test_sql 거부: {e}")
    shop_db = common.env("SHOP_DB", "shop")
    conn = common.connect(common.env("VERIFY_HOST", required=True), common.env("VERIFY_SECRET_ARN", required=True), shop_db)
    try:
        r = run(conn, ddl, p["test_sql"], shop_db, int(common.env("VERIFY_MAX_EXEC_MS", "60000")))
    finally:
        conn.close()
    if r.get("skipped"):
        return dict(base, status="SKIPPED", reason=r["skipped"])
    return common.jsonable(dict(base, status="PASS" if r["pass"] else "FAIL", ddl=ddl,
                                before_sec=r["before"], after_sec=r["after"], same=r["same"],
                                rolled_back_by_guard=r["rolled_back_by_guard"]))
