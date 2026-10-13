"""Track 단계: 그날 평균으로 해결 · 재발을 판정한다 — slowq.tickets.track 그대로 (0.5 / 0.8 히스테리시스)."""
from slowq import tickets as stickets

from . import common


def handler(event, context):
    log_date = common.resolve_log_date(event)
    store = common.store_conn()
    try:
        changed = stickets.track(store, log_date)
    finally:
        store.close()
    return {"log_date": log_date, "changed": [{"ticket_id": c[0], "from": c[1], "to": c[2]} for c in changed]}
