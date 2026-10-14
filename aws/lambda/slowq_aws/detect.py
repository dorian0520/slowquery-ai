"""Detect 단계: 검출 규칙(기준초과 · 신규 · 악화 · 급증)을 적용한다 — slowq.detect 그대로.

출력의 hits 는 Step Functions 상태 크기 제한(256KB)을 넘지 않게 상위 N개 · 쿼리 앞부분만 남긴다.
"""
import json

from slowq import detect as sdetect

from . import common

MAX_HITS = 200
TEXT_LIMIT = 400
MAX_BYTES = 80 * 1024  # IssueTickets 입력에서 hits가 중복 보관되어도 256KiB에 여유를 둔다


def compact(hits, limit=MAX_HITS):
    keep = ("cluster", "qhash", "exec_cnt", "total_sec", "avg_sec", "reasons")
    out, size = [], 2
    for h in hits[:limit]:
        row = common.jsonable(dict({k: h[k] for k in keep}, query_text=(h.get("query_text") or "")[:TEXT_LIMIT]))
        added = len(json.dumps(row, ensure_ascii=False).encode("utf-8")) + (2 if out else 0)
        if size + added > MAX_BYTES:
            break
        out.append(row)
        size += added
    return out


def handler(event, context):
    log_date = common.resolve_log_date(event)
    store = common.store_conn()
    try:
        hits = sdetect.run(store, log_date, common.rules())
    finally:
        store.close()
    rows = compact(hits)
    return common.jsonable({"log_date": log_date, "count": len(hits), "truncated": len(hits) - len(rows), "hits": rows})
