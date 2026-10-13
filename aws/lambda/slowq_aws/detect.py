"""Detect 단계: 검출 규칙(기준초과 · 신규 · 악화 · 급증)을 적용한다 — slowq.detect 그대로.

출력의 hits 는 Step Functions 상태 크기 제한(256KB)을 넘지 않게 상위 N개 · 쿼리 앞부분만 남긴다.
"""
from slowq import detect as sdetect

from . import common

MAX_HITS = 200
TEXT_LIMIT = 400


def compact(hits, limit=MAX_HITS):
    keep = ("cluster", "qhash", "exec_cnt", "total_sec", "avg_sec", "reasons")
    return [dict({k: h[k] for k in keep}, query_text=(h.get("query_text") or "")[:TEXT_LIMIT]) for h in hits[:limit]]


def handler(event, context):
    log_date = common.resolve_log_date(event)
    store = common.store_conn()
    try:
        hits = sdetect.run(store, log_date, common.rules())
    finally:
        store.close()
    return common.jsonable({"log_date": log_date, "count": len(hits), "hits": compact(hits)})
