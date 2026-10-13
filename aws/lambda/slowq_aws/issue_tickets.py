"""IssueTickets 단계: 검출 결과로 티켓을 중복 없이 발행하고(slowq.tickets.issue), AI 분석 후보를 고른다.

후보 = 아직 분석 결과가 없는 열린 티켓(OPEN · REOPENED), 총 부하 순 상위 ANALYZE_MAX 개 (Bedrock 비용 상한).
"""
from slowq import tickets as stickets

from . import common

CANDIDATE_SQL = """
SELECT t.ticket_id, t.cluster, t.qhash, d.query_text
FROM tuning_ticket t
JOIN slow_digest_daily d ON d.cluster = t.cluster AND d.qhash = t.qhash AND d.log_date = %s
WHERE t.status IN ('OPEN', 'REOPENED') AND t.recommendation IS NULL
ORDER BY d.total_sec DESC
LIMIT %s
"""


def candidates(store, log_date, limit):
    with store.cursor() as cur:
        cur.execute(CANDIDATE_SQL, (log_date, int(limit)))
        rows = cur.fetchall()
    return [dict(r, query_text=(r["query_text"] or "")[:2000], log_date=log_date) for r in rows]


def handler(event, context):
    log_date = common.resolve_log_date(event)
    hits = event.get("hits") or []
    rules = common.rules()
    store = common.store_conn()
    try:
        made = stickets.issue(store, log_date, hits, rules["top_n"])
        cands = candidates(store, log_date, int(common.env("ANALYZE_MAX", "5")))
    finally:
        store.close()
    return common.jsonable({"log_date": log_date, "made": made, "candidates": cands})
