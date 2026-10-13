"""섹션 9 · 관리: 주간 리포트 — 새로 생긴 문제, 해결 · 재발, 절감 시간, 오래 열린 티켓.

python3 report.py --end 2026-10-13          # 최근 7일
"""
import argparse, datetime as dt
from common import STORE, connect

OPEN = ("OPEN", "IN_PROGRESS", "REOPENED")
EVENT_STATUS = {"CREATED": "OPEN", "APPLIED": "IN_PROGRESS", "RESOLVED": "RESOLVED", "REOPENED": "REOPENED"}


def status_as_of(events, end):
    """티켓 이벤트로 end 날짜 시점의 상태를 되짚는다 — 지난 주 리포트도 그때 숫자 그대로 나오게."""
    st = None
    for e in sorted(events, key=lambda e: e["at"]):
        if e["at"].date() <= end and e["event"] in EVENT_STATUS:
            st = EVENT_STATUS[e["event"]]
    return st


def summarize(tickets, events, daily, end, days=7):
    start = end - dt.timedelta(days=days - 1)
    inside = lambda d: start <= d <= end
    base = {(t["cluster"], t["qhash"]): t["baseline_avg_sec"] for t in tickets}
    by_ticket = {}
    for e in events:
        by_ticket.setdefault(e["ticket_id"], []).append(e)

    def status(t):   # 이벤트가 있으면 그날 기준, 없으면 현재 상태(발행 전이면 제외)
        if t["ticket_id"] in by_ticket:
            return status_as_of(by_ticket[t["ticket_id"]], end)
        return t["status"] if t["created_at"].date() <= end else None
    opened = [t for t in tickets if status(t) in OPEN]
    team = {}
    for t in opened:
        team[t["owner_team"]] = team.get(t["owner_team"], 0) + 1
    saved = sum((base[(r["cluster"], r["qhash"])] - r["avg_sec"]) * r["exec_cnt"] for r in daily
                if (r["cluster"], r["qhash"]) in base and inside(r["log_date"])
                and r["avg_sec"] <= base[(r["cluster"], r["qhash"])] * 0.5)
    return {"start": start, "end": end,
            "new": sum(1 for t in tickets if inside(t["created_at"].date())),
            "resolved": len({e["ticket_id"] for e in events if e["event"] == "RESOLVED" and inside(e["at"].date())}),   # 티켓 수
            "reopened": len({e["ticket_id"] for e in events if e["event"] == "REOPENED" and inside(e["at"].date())}),
            "open": len(opened),
            "open_age_days": {t["ticket_id"]: (end - t["created_at"].date()).days for t in opened},
            "saved_sec": round(saved, 1),
            "open_by_team": dict(sorted(team.items()))}


def main(end, days):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute("""SELECT t.*, c.owner_team FROM tuning_ticket t JOIN cmdb_cluster c ON c.cluster=t.cluster""")
        tickets = cur.fetchall()
        cur.execute("SELECT ticket_id, at, event FROM ticket_event")
        events = cur.fetchall()
        cur.execute("SELECT cluster, qhash, log_date, avg_sec, exec_cnt, total_sec FROM slow_digest_daily")
        daily = cur.fetchall()
    r = summarize(tickets, events, daily, end, days)
    print(f"# 슬로우 쿼리 주간 리포트 ({r['start']} ~ {r['end']})\n")
    print(f"- 새 티켓 {r['new']}건 · 해결 {r['resolved']}건 · 재발 {r['reopened']}건 · 열린 티켓 {r['open']}건")
    print(f"- 이번 주 절감 시간 {r['saved_sec']}초 (해결 기준을 만족한 날의 (기준 - 실제) × 실행 횟수)")
    print("- 팀별 열린 티켓: " + ", ".join(f"{k} {v}건" for k, v in r["open_by_team"].items()))
    print("\n## 열린 티켓 (오래된 순)")
    by_id = {t["ticket_id"]: t for t in tickets}
    last = {}
    for d in daily:
        if d["log_date"] == end:
            last[(d["cluster"], d["qhash"])] = d
    for tid, age in sorted(r["open_age_days"].items(), key=lambda x: -x[1]):
        t = by_id[tid]; d = last.get((t["cluster"], t["qhash"]), {})
        st = status_as_of([e for e in events if e["ticket_id"] == tid], end) or t["status"]
        print(f"- #{tid} {t['cluster']} {t['qhash'][:8]} {st} · {age}일째 · 기준 {t['baseline_avg_sec']:.3f}s "
              f"→ {end} {d.get('avg_sec', 0):.3f}s · 하루 부하 {d.get('total_sec', 0):.1f}s · {t['owner_team']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--days", type=int, default=7)
    a = p.parse_args()
    main(dt.date.fromisoformat(a.end), a.days)
