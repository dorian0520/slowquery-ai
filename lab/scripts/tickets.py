"""섹션 6·7: 티켓 자동 발행과 추적

python3 tickets.py issue  --log-date 2026-10-12   # 검출 규칙에 걸린 쿼리 → 티켓 발행 (중복 없이)
python3 tickets.py track  --log-date 2026-10-13   # 개선 확인 → RESOLVED, 재발 → REOPENED
"""
import argparse, datetime as dt
from common import STORE, connect

MIN_SEC = 0.2        # 평균 실행 시간 기준 (실습 PC 기준. 운영에서는 보통 0.5~1초)
MIN_Q = 5            # 하루 최소 실행 횟수 (실습 규모에 맞춤)
TOP_N = 10           # 하루 발행 상한 (총 부하 순)
RESOLVE_RATIO = 0.5  # 기준 대비 절반 이하로 빨라지면 해결로 본다
REOPEN_RATIO = 0.8   # 해결 후 기준의 80% 이상으로 돌아오면 재발로 본다


def event(cur, ticket_id, ev, note, at):
    cur.execute("INSERT INTO ticket_event (ticket_id, at, event, note) VALUES (%s,%s,%s,%s)", (ticket_id, at, ev, note))


def issue(log_date):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute("""
            SELECT d.cluster, d.qhash, d.query_text, d.avg_sec, d.exec_cnt, d.total_sec,
                   c.owner, c.owner_team, c.slack_channel
            FROM slow_digest_daily d
            JOIN cmdb_cluster c ON c.cluster = d.cluster AND c.collect = 1   -- CMDB로 담당 팀·담당자 결정
            LEFT JOIN tuning_ticket t ON t.cluster = d.cluster AND t.qhash = d.qhash
            WHERE d.log_date = %s AND d.avg_sec >= %s AND d.exec_cnt >= %s AND t.ticket_id IS NULL
            ORDER BY d.total_sec DESC LIMIT %s
        """, (log_date, MIN_SEC, MIN_Q, TOP_N))
        rows = cur.fetchall()
        for r in rows:
            title = f"[슬로우쿼리] {r['cluster']} {r['qhash'][:8]} 평균 {r['avg_sec']:.2f}s × {r['exec_cnt']}회"
            cur.execute("""INSERT INTO tuning_ticket (cluster, qhash, title, owner, baseline_avg_sec, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (r["cluster"], r["qhash"], title, r["owner"], r["avg_sec"], f"{log_date} 09:00:00"))
            event(cur, cur.lastrowid, "CREATED",
                  f"총 부하 {r['total_sec']:.0f}s · 담당 {r['owner_team']}/{r['owner']} · 알림 {r['slack_channel']}",
                  f"{log_date} 09:00:00")
            print("발행:", title, "→", r["owner_team"])
        print(f"{log_date}: 신규 티켓 {len(rows)}건")


def track(log_date):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute("""
            SELECT t.ticket_id, t.status, t.baseline_avg_sec, d.avg_sec
            FROM tuning_ticket t
            JOIN slow_digest_daily d ON d.cluster = t.cluster AND d.qhash = t.qhash AND d.log_date = %s
        """, (log_date,))
        for r in cur.fetchall():
            base, now = r["baseline_avg_sec"], r["avg_sec"]
            if r["status"] in ("OPEN", "IN_PROGRESS", "REOPENED") and now <= base * RESOLVE_RATIO:
                cur.execute("""UPDATE tuning_ticket SET status='RESOLVED', after_avg_sec=%s, verified=1,
                               resolved_at=%s WHERE ticket_id=%s""", (now, f"{log_date} 09:00:00", r["ticket_id"]))
                event(cur, r["ticket_id"], "RESOLVED", f"{base:.2f}s → {now:.2f}s", f"{log_date} 09:00:00")
                print(f"#{r['ticket_id']} 해결 확인 {base:.2f}s → {now:.2f}s")
            elif r["status"] == "RESOLVED" and now >= base * REOPEN_RATIO:
                cur.execute("UPDATE tuning_ticket SET status='REOPENED' WHERE ticket_id=%s", (r["ticket_id"],))
                event(cur, r["ticket_id"], "REOPENED", f"재발 {now:.2f}s (기준 {base:.2f}s)", f"{log_date} 09:00:00")
                print(f"#{r['ticket_id']} 재발 → 다시 열림")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["issue", "track"])
    p.add_argument("--log-date", default=dt.date.today().isoformat())
    a = p.parse_args()
    (issue if a.cmd == "issue" else track)(a.log_date)
