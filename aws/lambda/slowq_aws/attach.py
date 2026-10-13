"""Attach 단계: AI 분석 · 실측 검증 결과를 티켓에 붙이고 이벤트를 남긴다 (lab publish.py attach 와 같은 규칙).

- 분석 형식 오류 · 답 없음도 기록한다 → 같은 티켓을 매일 다시 분석하지 않고 사람이 본다.
- 이벤트는 같은 티켓 · 같은 시각에 한 번만 (다시 실행해도 중복 없음).
"""
import json

from . import common


def recommendation(analysis, verify):
    a, v = analysis or {}, verify or {}
    if a.get("status") != "OK":
        return {"status": a.get("status") or "ERROR", "error": a.get("error"), "verify": None}, \
            f"AI {a.get('status') or 'ERROR'} → 사람 검토"
    p = a["proposal"]
    rec = {k: p.get(k) for k in ("cause", "evidence", "proposal", "expected", "confidence", "test_sql")}
    rec["status"] = "OK"
    rec["verify"] = {k: v.get(k) for k in ("status", "reason", "ddl", "before_sec", "after_sec", "same")}
    rec["verify"]["pass"] = v.get("status") == "PASS"
    note = {"PASS": "실측 통과", "FAIL": "실측 탈락 → 사람 검토"}.get(v.get("status"), f"검증 없음({v.get('reason', '-')})")
    return rec, f"{p.get('confidence')} · {note}"


def attach(store, ticket_id, log_date, analysis, verify):
    rec, note = recommendation(analysis, verify)
    at = f"{log_date} 10:00:00"
    with store.cursor() as cur:
        cur.execute("UPDATE tuning_ticket SET recommendation=%s, verified=%s WHERE ticket_id=%s",
                    (json.dumps(rec, ensure_ascii=False), 1 if (rec.get("verify") or {}).get("pass") else 0, ticket_id))
        cur.execute("""INSERT INTO ticket_event (ticket_id, at, event, note)
                       SELECT %s, %s, 'AI_ANALYZED', %s FROM DUAL WHERE NOT EXISTS (
                         SELECT 1 FROM ticket_event WHERE ticket_id=%s AND event='AI_ANALYZED' AND at=%s)""",
                    (ticket_id, at, note[:500], ticket_id, at))
    return note


def handler(event, context):
    t = event["ticket"]
    store = common.store_conn()
    try:
        note = attach(store, t["ticket_id"], t["log_date"], event.get("analysis"), event.get("verify"))
    finally:
        store.close()
    return {"ticket_id": t["ticket_id"], "note": note}
