"""섹션 4 · 17강: 검출 규칙 — 기준 초과 · 신규 · 악화 · 급증

python3 detect.py --log-date 2026-10-06
"""
import argparse, datetime as dt
from common import STORE, connect

MIN_SEC, MIN_Q = 0.2, 5      # 기준 초과 (실습 PC 기준)
BASE_DAYS = 7                # 비교 기간
WORSE_RATIO = 2.0            # 평균 시간이 직전일 대비 2배 이상 → 악화
SPIKE_RATIO = 2.0            # 실행 횟수가 기준 대비 2배 이상 → 급증

SQL = """
WITH today AS (
  SELECT cluster, qhash, query_text, exec_cnt, avg_sec, total_sec
  FROM slow_digest_daily WHERE log_date = %(d)s
), prev AS (           -- 직전일: 평균이 섞이지 않은 비교 대상
  SELECT cluster, qhash, avg_sec FROM slow_digest_daily WHERE log_date = %(d)s - INTERVAL 1 DAY
), base AS (
  SELECT cluster, qhash, AVG(exec_cnt) cnt, AVG(avg_sec) avg_s, COUNT(*) days
  FROM slow_digest_daily
  WHERE log_date >= %(d)s - INTERVAL %(n)s DAY AND log_date < %(d)s
  GROUP BY cluster, qhash
)
SELECT t.cluster, LEFT(t.qhash, 8) qhash, LEFT(REPLACE(t.query_text, '`', ''), 40) q,
       t.exec_cnt, ROUND(t.avg_sec, 3) avg_s, ROUND(b.cnt, 1) base_cnt, ROUND(b.avg_s, 3) base_avg,
       ROUND(p.avg_sec, 4) prev_avg,
       CONCAT_WS(',',
         IF(t.avg_sec >= %(min_sec)s AND t.exec_cnt >= %(min_q)s, '기준초과', NULL),
         IF(b.qhash IS NULL AND t.exec_cnt >= %(min_q)s, '신규', NULL),
         IF(p.avg_sec > 0 AND t.avg_sec >= p.avg_sec * %(worse)s AND t.avg_sec >= %(min_sec)s AND t.exec_cnt >= %(min_q)s, '악화', NULL),
         IF(b.cnt > 0 AND t.exec_cnt >= b.cnt * %(spike)s AND t.total_sec >= 1, '급증', NULL)) AS rules
FROM today t
LEFT JOIN base b ON b.cluster = t.cluster AND b.qhash = t.qhash
LEFT JOIN prev p ON p.cluster = t.cluster AND p.qhash = t.qhash
WHERE t.query_text NOT REGEXP '^(ALTER|CREATE|DROP|TRUNCATE|SET|SHOW|ANALYZE)'   -- 일회성 관리 작업 제외
HAVING rules <> ''
ORDER BY t.total_sec DESC
"""


def detect(log_date):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute(SQL, {"d": log_date, "n": BASE_DAYS, "min_sec": MIN_SEC, "min_q": MIN_Q,
                          "worse": WORSE_RATIO, "spike": SPIKE_RATIO})
        rows = cur.fetchall()
    print(f"[{log_date}] 검출 {len(rows)}건")
    for r in rows:
        print(f"  {r['cluster']:<8} {r['qhash']}  {r['rules']:<12} 오늘 {r['exec_cnt']:>4}회 {r['avg_s']:.3f}s"
              f"  | 기준 {r['base_cnt'] or '-'}회 · 직전일 {r['prev_avg'] if r['prev_avg'] is not None else '-'}s  {r['q']}")
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--log-date", default=dt.date.today().isoformat())
    detect(p.parse_args().log_date)
