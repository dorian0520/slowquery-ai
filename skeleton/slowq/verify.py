"""실측 검증: AI 제안 DDL 을 검증 DB 에만 적용해 전후를 재고, 반드시 되돌린다."""
import hashlib
import re
import time

PASS_RATIO = 0.5   # 절반 이하로 빨라지고 결과가 같아야 통과

IDX = re.compile(r"\s*ALTER\s+TABLE\s+([`\w.]+)\s+ADD\s+(?:INDEX|KEY)\s+`?(\w+)`?\s*(\([^()]*\))\s*;?\s*", re.I)


def index_target(ddl):
    """ADD INDEX 한 절만 있는 DDL 이면 (테이블, 인덱스, 실행할 DDL). 다른 절이 붙으면 되돌릴 수 없으므로 None."""
    m = IDX.fullmatch(ddl or "")
    return (m.group(1), m.group(2), f"ALTER TABLE {m.group(1)} ADD INDEX {m.group(2)} {m.group(3)}") if m else None


def result_digest(rows):
    """결과 동일성 — 행 순서는 무시한다 (인덱스가 생기면 ORDER BY 없는 결과 순서가 바뀔 수 있다)."""
    return hashlib.md5(repr(sorted(rows, key=repr)).encode()).hexdigest()


def judge(before, after, same):
    return same and after <= before * PASS_RATIO


def _measure(cur, sql, n=3):
    times, digest = [], None
    for _ in range(n):
        t = time.perf_counter(); cur.execute(sql); rows = cur.fetchall(); times.append(time.perf_counter() - t)
        digest = result_digest(rows)
    return min(times), digest


def verify(conn, ddl, test_sql):
    """검증 DB 연결에서 한 건을 검증. {'pass', 'before', 'after', 'same'} 또는 실행하지 않은 이유."""
    target = index_target(ddl)
    if not target:
        return {"pass": False, "skipped": f"되돌릴 수 없는 DDL: {ddl[:80]}"}
    table, idx, safe_ddl = target
    with conn.cursor() as cur:
        b_t, b_d = _measure(cur, test_sql)
        cur.execute(safe_ddl)                 # 원문이 아니라 검사한 절만 다시 만들어 실행한다
        try:
            a_t, a_d = _measure(cur, test_sql)
        finally:
            cur.execute(f"ALTER TABLE {table} DROP INDEX {idx}")
    return {"pass": judge(b_t, a_t, b_d == a_d), "before": b_t, "after": a_t, "same": b_d == a_d}
