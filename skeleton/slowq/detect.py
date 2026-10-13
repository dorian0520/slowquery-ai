"""검출 규칙: 기준초과 · 신규 · 악화(직전일 대비) · 급증(7일 평균 대비). DDL · SET · SHOW 는 모든 규칙에서 제외."""
import re

NON_BUSINESS = re.compile(r"^\s*(ALTER|CREATE|DROP|TRUNCATE|RENAME|ANALYZE|OPTIMIZE|SET|SHOW)\b", re.I)

HISTORY_SQL = """
SELECT t.cluster, t.qhash,
       (SELECT p.avg_sec FROM slow_digest_daily p WHERE p.cluster=t.cluster AND p.qhash=t.qhash
          AND p.log_date = %(d)s - INTERVAL 1 DAY) AS prev_avg,
       (SELECT AVG(p.exec_cnt) FROM slow_digest_daily p WHERE p.cluster=t.cluster AND p.qhash=t.qhash
          AND p.log_date >= %(d)s - INTERVAL %(days)s DAY AND p.log_date < %(d)s) AS avg_cnt
FROM slow_digest_daily t WHERE t.log_date = %(d)s
"""


def detect(today, history, rules, known=None):
    """today: 그날 일자별 행, history: {(cluster,qhash): {prev_avg, avg_cnt}}, known: 이전에 본 (cluster,qhash) 집합(없으면 신규 판정 생략)."""
    hits = []
    seen_clusters = {c for c, _ in known} if known else set()
    for r in today:
        if NON_BUSINESS.match(r["query_text"] or ""):
            continue
        key = (r["cluster"], r["qhash"])
        h = history.get(key) or {}
        enough = r["exec_cnt"] >= rules["min_q"]
        reasons = []
        if enough and r["avg_sec"] >= rules["min_sec"]:
            reasons.append("기준초과")
        if known is not None and r["cluster"] in seen_clusters and key not in known and enough:   # 이력이 있는 클러스터에서만
            reasons.append("신규")
        prev = float(h["prev_avg"]) if h.get("prev_avg") else None      # MySQL 은 Decimal 을 돌려준다
        if enough and prev and r["avg_sec"] >= rules["min_sec"] and r["avg_sec"] >= prev * rules["worse_ratio"]:
            reasons.append("악화")
        avg_cnt = float(h["avg_cnt"]) if h.get("avg_cnt") else None
        if avg_cnt and r["exec_cnt"] >= avg_cnt * rules["spike_ratio"] and r["total_sec"] >= rules["spike_min_total"]:
            reasons.append("급증")
        if reasons:
            hits.append(dict(r, reasons=reasons))
    return sorted(hits, key=lambda x: -x["total_sec"])


def run(store, log_date, rules, days=7):
    with store.cursor() as cur:
        cur.execute("SELECT * FROM slow_digest_daily WHERE log_date=%s", (log_date,))
        today = cur.fetchall()
        cur.execute(HISTORY_SQL, {"d": log_date, "days": days})
        history = {(r["cluster"], r["qhash"]): r for r in cur.fetchall()}
        cur.execute("""SELECT DISTINCT cluster, qhash FROM slow_digest_daily
                       WHERE log_date >= %s - INTERVAL %s DAY AND log_date < %s""", (log_date, days, log_date))  # 신규 = 지난 7일에 없던 지문
        known = {(r["cluster"], r["qhash"]) for r in cur.fetchall()}
    return detect(today, history, rules, known if known else None)
