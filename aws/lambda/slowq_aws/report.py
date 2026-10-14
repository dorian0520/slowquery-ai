"""Report 단계 (주 1회): 주간 리포트를 Markdown · HTML 로 만들어 S3 에 올린다.

집계 규칙은 lab/scripts/report.py 와 같다 — 새 티켓 · 해결 · 재발 · 열린 티켓 · 절감 시간 · 팀별 열린 티켓.
지난 주 리포트를 다시 만들어도 그때 숫자가 나오도록, 상태는 이벤트로 되짚는다.
"""
import datetime as dt
import html

from . import common

OPEN = ("OPEN", "IN_PROGRESS", "REOPENED")
EVENT_STATUS = {"CREATED": "OPEN", "APPLIED": "IN_PROGRESS", "RESOLVED": "RESOLVED", "REOPENED": "REOPENED"}


def _d(v):
    return v.date() if isinstance(v, dt.datetime) else v


def status_as_of(events, end):
    st = None
    for e in sorted(events, key=lambda e: e["at"]):
        if _d(e["at"]) <= end and e["event"] in EVENT_STATUS:
            st = EVENT_STATUS[e["event"]]
    return st


def summarize(tickets, events, daily, end, days=7):
    start = end - dt.timedelta(days=days - 1)
    inside = lambda d: start <= _d(d) <= end                                   # noqa: E731
    base = {(t["cluster"], t["qhash"]): float(t["baseline_avg_sec"]) for t in tickets}
    by_ticket = {}
    for e in events:
        by_ticket.setdefault(e["ticket_id"], []).append(e)

    def status(t):
        if t["ticket_id"] in by_ticket:
            return status_as_of(by_ticket[t["ticket_id"]], end)
        return t["status"] if _d(t["created_at"]) <= end else None

    opened = [t for t in tickets if status(t) in OPEN]
    team = {}
    for t in opened:
        team[t["owner_team"]] = team.get(t["owner_team"], 0) + 1
    saved = sum((base[(r["cluster"], r["qhash"])] - float(r["avg_sec"])) * int(r["exec_cnt"]) for r in daily
                if (r["cluster"], r["qhash"]) in base and inside(r["log_date"])
                and float(r["avg_sec"]) <= base[(r["cluster"], r["qhash"])] * 0.5)
    return {"start": start, "end": end,
            "new": sum(1 for t in tickets if inside(t["created_at"])),
            "resolved": len({e["ticket_id"] for e in events if e["event"] == "RESOLVED" and inside(e["at"])}),
            "reopened": len({e["ticket_id"] for e in events if e["event"] == "REOPENED" and inside(e["at"])}),
            "open": len(opened),
            "open_age_days": {t["ticket_id"]: (end - _d(t["created_at"])).days for t in opened},
            "saved_sec": round(saved, 1),
            "open_by_team": dict(sorted(team.items()))}


def to_markdown(r, tickets):
    by_id = {t["ticket_id"]: t for t in tickets}
    lines = [f"# 슬로우 쿼리 주간 리포트 ({r['start']} ~ {r['end']})", "",
             f"- 새 티켓 {r['new']}건 · 해결 {r['resolved']}건 · 재발 {r['reopened']}건 · 열린 티켓 {r['open']}건",
             f"- 이번 주 절감 시간 {r['saved_sec']}초 (해결 기준을 만족한 날의 (기준 - 실제) × 실행 횟수)",
             "- 팀별 열린 티켓: " + (", ".join(f"{k} {v}건" for k, v in r["open_by_team"].items()) or "없음"),
             "", "## 열린 티켓 (오래된 순)", ""]
    for tid, age in sorted(r["open_age_days"].items(), key=lambda x: -x[1]):
        t = by_id[tid]
        lines.append(f"- #{tid} {t['cluster']} {t['qhash'][:8]} · {age}일째 · 기준 {float(t['baseline_avg_sec']):.3f}s "
                     f"· {t['owner_team']}")
    return "\n".join(lines) + "\n"


def to_html(md):
    """Markdown 을 그대로 감싼 자기완결 HTML (외부 리소스 없음)."""
    body = []
    for ln in md.splitlines():
        e = html.escape(ln)
        if ln.startswith("# "):
            body.append(f"<h1>{e[2:]}</h1>")
        elif ln.startswith("## "):
            body.append(f"<h2>{e[3:]}</h2>")
        elif ln.startswith("- "):
            body.append(f"<li>{e[2:]}</li>")
        elif ln.strip():
            body.append(f"<p>{e}</p>")
    return ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>슬로우 쿼리 주간 리포트</title>"
            "<style>body{font-family:sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.6}</style>"
            "</head><body>" + "\n".join(body) + "</body></html>\n")


def load(store, start, end):
    with store.cursor() as cur:
        cur.execute("SELECT t.*, c.owner_team FROM tuning_ticket t JOIN cmdb_cluster c ON c.cluster=t.cluster")
        tickets = cur.fetchall()
        cur.execute("SELECT ticket_id, at, event FROM ticket_event")
        events = cur.fetchall()
        cur.execute("""SELECT cluster, qhash, log_date, avg_sec, exec_cnt FROM slow_digest_daily
                       WHERE log_date BETWEEN %s AND %s""", (start, end))
        daily = cur.fetchall()
    return tickets, events, daily


def handler(event, context, s3=None):
    end = dt.date.fromisoformat(common.resolve_log_date(event))
    days = int((event or {}).get("days", 7))
    if not 1 <= days <= 366:
        raise ValueError("days 는 1~366 사이여야 합니다")
    store = common.store_conn()
    try:
        tickets, events, daily = load(store, end - dt.timedelta(days=days - 1), end)
    finally:
        store.close()
    r = summarize(tickets, events, daily, end, days)
    md = to_markdown(r, tickets)
    if s3 is None:
        import boto3
        s3 = boto3.client("s3")
    bucket = common.env("REPORT_BUCKET", required=True)
    keys = {}
    for ext, body, ctype in (("md", md, "text/markdown; charset=utf-8"), ("html", to_html(md), "text/html; charset=utf-8")):
        key = f"reports/{end.isoformat()}/weekly.{ext}"
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType=ctype)
        keys[ext] = f"s3://{bucket}/{key}"
    return common.jsonable({"end": end, "summary": {k: r[k] for k in ("new", "resolved", "reopened", "open", "saved_sec")},
                            "objects": keys})
