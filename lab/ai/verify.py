"""섹션 5 · 26강: AI 개선안 실측 검증 — 결과(통과 · 탈락)를 남기고, 운영 반영은 통과한 것만 (38강)

검증 DB(order-db, 운영과 같은 데이터의 복제본 역할)에만 DDL 을 적용하고
① 실행 시간 ② 결과 동일성을 전후 비교하고(실행 계획 마지막 줄도 함께 출력) DDL 을 되돌린다.
python3 verify.py run1.txt
"""
import json, re, sys, time, hashlib
import pymysql

VERIFY = dict(host="127.0.0.1", port=3307, user="root", password="lab-root-pw", database="shop")
# 쿼리 지문별 검증용 테스트 쿼리 (값은 테스트 값)
TEST_SQL = {
    "5e9245c3092ff8032ccbe00d8fa31da9":
        "SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20",
    "f54ce51c10b421111d1ef8531c86b405":
        "SELECT order_id, user_id, amount FROM orders ORDER BY ordered_at DESC LIMIT 100000, 20",
    "60cd58c264505a96829053fba16859a7":
        "SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29'",
}
PASS_RATIO = 0.5   # 절반 이하로 빨라져야 통과
IDX = re.compile(r"\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+(?:INDEX|KEY)\s+(\w+)\s*(\([^()]*\))\s*;?\s*", re.I)


def safe_index_ddl(ddl):
    """ADD INDEX 한 절만 있는 DDL 이면 (테이블, 인덱스, 다시 만든 DDL). 다른 절이 붙으면 되돌릴 수 없으므로 None."""
    m = IDX.fullmatch(ddl or "")
    return (m.group(1), m.group(2), f"ALTER TABLE {m.group(1)} ADD INDEX {m.group(2)} {m.group(3)}") if m else None


def measure(cur, sql, n=3):
    times, digest = [], None
    for _ in range(n):
        t = time.perf_counter(); cur.execute(sql); rows = cur.fetchall(); times.append(time.perf_counter() - t)
        digest = hashlib.md5(repr(rows).encode()).hexdigest()   # 결과 동일성 확인용
    cur.execute("EXPLAIN ANALYZE " + sql)
    plan = cur.fetchone()[0]
    examined = sum(float(x) for x in re.findall(r"actual time=[\d.e+-]+\.\.[\d.e+-]+ rows=([\d.e+]+)", plan)[-1:])
    return min(times), digest, examined, plan.splitlines()[-1].strip()[:90]


def main(path):
    text = open(path).read()
    try:
        proposals = json.loads(text[text.index("["): text.rindex("]") + 1])
    except ValueError as e:   # AI 가 형식을 어기면 아무것도 검증 · 발행하지 않고 멈춘다
        sys.exit(f"AI 출력이 올바른 JSON 배열이 아닙니다 → 검증 중단 ({e}). 분석을 다시 실행하거나 사람이 확인하세요.")
    conn = pymysql.connect(**VERIFY, autocommit=True); cur = conn.cursor()
    for p in proposals:
        sql = TEST_SQL.get(p["qhash"])
        ddls = re.findall(r"ALTER TABLE[^;]+", p["proposal"])
        if not sql or not ddls:
            print(f"[{p['qhash'][:8]}] 건너뜀 — 테스트 쿼리 또는 DDL 없음"); continue
        target = safe_index_ddl(ddls[0])
        if not target:
            print(f"[{p['qhash'][:8]}] 건너뜀 — 되돌릴 수 없는 DDL: {ddls[0].strip()}"); continue
        table, idx, ddl = target
        b_t, b_d, b_rows, b_plan = measure(cur, sql)
        cur.execute(ddl)                                             # 검사한 한 절만 다시 만들어 실행
        try:
            a_t, a_d, a_rows, a_plan = measure(cur, sql)
        finally:
            cur.execute(f"ALTER TABLE {table} DROP INDEX {idx}")      # 검증 후 반드시 되돌림
        same = b_d == a_d
        ok = same and a_t <= b_t * PASS_RATIO
        print(f"[{p['qhash'][:8]}] {'통과' if ok else '탈락'}  {ddl}")
        print(f"    시간 {b_t*1000:.1f} ms → {a_t*1000:.2f} ms ({b_t / a_t:.0f}배) · 결과 동일 {same}")
        print(f"    전: {b_plan}")
        print(f"    후: {a_plan}")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run1.txt")
