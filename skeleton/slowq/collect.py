"""수집: performance_schema digest 누적값 → 직전 스냅숏과의 차이 = 기간 실행분."""
import datetime as dt

PS = 1e12  # 피코초 → 초

DIGEST_SQL = """
SELECT DIGEST AS digest, IFNULL(SCHEMA_NAME, '') AS schema_name, DIGEST_TEXT AS digest_text,
       COUNT_STAR AS count_star, SUM_TIMER_WAIT AS sum_timer_wait,
       SUM_ROWS_EXAMINED AS sum_rows_examined, FIRST_SEEN AS first_seen
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL                     -- 기본 DB 없이 접속한 앱의 쿼리도 '' 스키마로 수집
  AND IFNULL(SCHEMA_NAME, '') NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
  AND IFNULL(SCHEMA_NAME, '') <> %s          -- 저장소 자신의 쿼리는 수집하지 않는다
"""


def delta_rows(prev, cur):
    """prev: {(schema_name, digest): 직전 스냅숏 행}, cur: [현재 행] → 실행이 있었던 지문의 차이 목록.

    서버 재시작 · TRUNCATE 로 누적값이 리셋되면(FIRST_SEEN 이 바뀌거나 횟수가 줄면) 현재 값 전체를 기간 실행분으로 본다.
    """
    out = []
    for c in cur:
        p = prev.get((c["schema_name"], c["digest"]))   # 같은 지문도 스키마별로 따로 집계된다
        reset = p is None or str(p["first_seen"]) != str(c["first_seen"]) or c["count_star"] < p["count_star"]
        base = {"count_star": 0, "sum_timer_wait": 0, "sum_rows_examined": 0} if reset else p
        cnt = c["count_star"] - base["count_star"]
        if cnt <= 0:
            continue
        total = (c["sum_timer_wait"] - base["sum_timer_wait"]) / PS
        out.append({"qhash": c["digest"][:32], "query_text": c["digest_text"], "exec_cnt": cnt,
                    "total_sec": total, "avg_sec": total / cnt,
                    "rows_examined": c["sum_rows_examined"] - base["sum_rows_examined"]})
    return out


def collect(store, target_conn, cluster, log_date, snap_at=None, exclude_schema=""):
    """target_conn 의 digest 를 읽어 store 에 스냅숏 · 일자별 차이를 저장하고, 저장한 행 수를 돌려준다."""
    snap_at = snap_at or dt.datetime.now()          # 마이크로초까지 — 같은 초에 두 번 돌아도 겹치지 않게
    with target_conn.cursor() as cur:
        cur.execute(DIGEST_SQL, (exclude_schema,))
        now = cur.fetchall()
    with store.cursor() as cur:
        cur.execute("SELECT MAX(snap_at) AS t FROM digest_snapshot WHERE cluster=%s", (cluster,))
        last = cur.fetchone()["t"]
        prev = {}
        if last:
            cur.execute("SELECT * FROM digest_snapshot WHERE cluster=%s AND snap_at=%s", (cluster, last))
            prev = {(r["schema_name"], r["digest"]): r for r in cur.fetchall()}
        cur.executemany(
            """INSERT INTO digest_snapshot (snap_at, cluster, digest, schema_name, digest_text, count_star,
                                            sum_timer_wait, sum_rows_examined, first_seen)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(snap_at, cluster, r["digest"], r["schema_name"], r["digest_text"], r["count_star"],
              r["sum_timer_wait"], r["sum_rows_examined"], r["first_seen"]) for r in now])
        if not last:          # 첫 실행은 기준 스냅숏만 남긴다 (누적값을 하루치로 오인하지 않게)
            return 0
        rows = delta_rows(prev, now)
        cur.executemany(
            """INSERT INTO slow_digest_daily (log_date, cluster, qhash, query_text, exec_cnt, total_sec, avg_sec, rows_examined)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE exec_cnt = exec_cnt + VALUES(exec_cnt), total_sec = total_sec + VALUES(total_sec),
                                       avg_sec = total_sec / exec_cnt, rows_examined = rows_examined + VALUES(rows_examined)""",
            [(log_date, cluster, r["qhash"], r["query_text"], r["exec_cnt"], r["total_sec"], r["avg_sec"],
              r["rows_examined"]) for r in rows])
        return len(rows)
