"""섹션 4: 쿼리 지문(digest) 수집 → 일자별 집계

performance_schema 의 digest 통계는 누적값이라, 직전 스냅숏과의 차이(delta)를 하루치로 본다.
python3 collector.py --log-date 2026-10-12
"""
import argparse, datetime as dt
from common import CLUSTERS, STORE, connect

PS_SQL = """
SELECT DIGEST AS digest, IFNULL(SCHEMA_NAME, '') AS schema_name, DIGEST_TEXT AS digest_text,
       COUNT_STAR AS count_star, SUM_TIMER_WAIT AS sum_timer_wait,
       MAX_TIMER_WAIT AS max_timer_wait, SUM_ROWS_EXAMINED AS sum_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND SCHEMA_NAME NOT IN ('performance_schema', 'mysql', 'sys', 'dba')
"""
PS = 1e12  # 피코초 → 초


def snapshot(store, cluster, snap_at):
    with connect(cluster) as src, src.cursor() as cur:
        cur.execute(PS_SQL)
        rows = cur.fetchall()
    with store.cursor() as cur:
        cur.executemany(
            "INSERT INTO digest_snapshot VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(snap_at, cluster, r["digest"], r["schema_name"], r["digest_text"], r["count_star"],
              r["sum_timer_wait"], r["max_timer_wait"], r["sum_rows_examined"]) for r in rows])
    return len(rows)


def aggregate(store, cluster, snap_at, log_date):
    """이번 스냅숏 - 직전 스냅숏 = 하루치. 카운터가 줄었으면(재시작) 이번 값을 그대로 쓴다."""
    with store.cursor() as cur:
        cur.execute("SELECT MAX(snap_at) p FROM digest_snapshot WHERE cluster=%s AND snap_at < %s",
                    (cluster, snap_at))
        prev = cur.fetchone()["p"]
        cur.execute("""
            INSERT INTO slow_digest_daily
              (log_date, cluster, qhash, schema_name, query_text, exec_cnt, total_sec, avg_sec, max_sec, rows_examined)
            SELECT %s, x.cluster, LEFT(x.digest, 32), MIN(x.schema_name), MIN(x.digest_text),
                   SUM(x.cnt), SUM(x.wait) / %s, SUM(x.wait) / %s / SUM(x.cnt), MAX(x.max_wait) / %s, SUM(x.rows_ex)
            FROM (
              SELECT c.cluster, c.digest, c.schema_name, c.digest_text, c.max_timer_wait AS max_wait, d.cnt, d.wait, d.rows_ex
              FROM digest_snapshot c
              LEFT JOIN digest_snapshot p
                ON p.snap_at = %s AND p.cluster = c.cluster AND p.schema_name = c.schema_name AND p.digest = c.digest
              JOIN LATERAL (
                SELECT IF(p.count_star IS NULL OR c.count_star < p.count_star, c.count_star, c.count_star - p.count_star) cnt,
                       IF(p.count_star IS NULL OR c.count_star < p.count_star, c.sum_timer_wait, c.sum_timer_wait - p.sum_timer_wait) wait,
                       IF(p.count_star IS NULL OR c.count_star < p.count_star, c.sum_rows_examined, c.sum_rows_examined - p.sum_rows_examined) rows_ex
              ) d
              WHERE c.snap_at = %s AND c.cluster = %s AND d.cnt > 0
            ) x
            GROUP BY x.cluster, x.digest          -- 같은 지문이 여러 스키마에 있으면 하루 한 행으로 합친다
            ON DUPLICATE KEY UPDATE           -- 같은 날 두 번 수집하면 두 구간의 실행분을 더한다
              exec_cnt = exec_cnt + VALUES(exec_cnt), total_sec = total_sec + VALUES(total_sec),
              avg_sec = total_sec / exec_cnt, max_sec = GREATEST(max_sec, VALUES(max_sec)),
              rows_examined = rows_examined + VALUES(rows_examined)
        """, (log_date, PS, PS, PS, prev, snap_at, cluster))
        return cur.rowcount


def main(log_date):
    snap_at = dt.datetime.now().replace(microsecond=0)
    with connect(STORE, db="dba") as store:
        with store.cursor() as cur:  # 수집 대상은 CMDB가 정한다
            cur.execute("SELECT cluster FROM cmdb_cluster WHERE collect = 1")
            targets = [r["cluster"] for r in cur.fetchall() if r["cluster"] in CLUSTERS]
        for cluster in targets:
            n = snapshot(store, cluster, snap_at)
            m = aggregate(store, cluster, snap_at, log_date)
            print(f"{log_date} {cluster}: digest {n}개 수집, 일자 집계 {m}건")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--log-date", default=dt.date.today().isoformat())
    main(p.parse_args().log_date)
