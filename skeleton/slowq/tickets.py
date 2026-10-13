"""티켓: CMDB 담당자로 중복 없이 발행하고, 수치로 해결 · 재발을 판정한다."""
import pymysql

RESOLVE_RATIO = 0.5   # 기준의 절반 이하 → 해결
REOPEN_RATIO = 0.8    # 해결 후 기준의 80% 이상 → 재발 (사이 구간은 유지해 상태가 흔들리지 않게)


def next_status(status, base, now):
    if now is None:                       # 그날 실행 없음 = 판단 보류
        return status
    if status in ("OPEN", "IN_PROGRESS", "REOPENED") and now <= base * RESOLVE_RATIO:
        return "RESOLVED"
    if status == "RESOLVED" and now >= base * REOPEN_RATIO:
        return "REOPENED"
    return status


def issuable(hit):
    """발행은 기준초과(악화 포함)만 — 신규 · 급증은 검출 목록으로 보고 사람이 판단한다 (해결 판정이 평균 시간 기준이므로)."""
    return "기준초과" in hit["reasons"]


def _event(cur, ticket_id, at, ev, note):
    cur.execute("INSERT INTO ticket_event (ticket_id, at, event, note) VALUES (%s,%s,%s,%s)", (ticket_id, at, ev, note))


def issue(store, log_date, hits, top_n=10):
    """검출 결과(hits) 중 티켓이 없는 것만 총 부하 순으로 발행. 발행한 티켓 목록을 돌려준다."""
    made = []
    with store.cursor() as cur:
        for h in (h for h in hits if issuable(h)):
            if len(made) >= top_n:        # 상한은 새로 발행한 것만 센다 (이미 티켓이 있는 쿼리는 자리를 차지하지 않는다)
                break
            cur.execute("""SELECT owner, owner_team, slack_channel FROM cmdb_cluster WHERE cluster=%s AND collect=1""",
                        (h["cluster"],))
            c = cur.fetchone()
            if not c:
                continue                  # CMDB 에 없거나 수집 제외된 클러스터는 발행하지 않는다
            title = f"[슬로우쿼리] {h['cluster']} {h['qhash'][:8]} 평균 {h['avg_sec']:.2f}s × {h['exec_cnt']}회"
            try:
                cur.execute("""INSERT INTO tuning_ticket (cluster, qhash, title, owner, baseline_avg_sec, created_at)
                               VALUES (%s,%s,%s,%s,%s,%s)""",
                            (h["cluster"], h["qhash"], title, c["owner"], h["avg_sec"], f"{log_date} 09:00:00"))
            except pymysql.err.IntegrityError as e:
                if e.args[0] != 1062:     # UNIQUE(cluster, qhash) 중복만 건너뛰고, 다른 오류는 그대로 알린다
                    raise
                continue
            tid = cur.lastrowid
            _event(cur, tid, f"{log_date} 09:00:00", "CREATED", f"{','.join(h['reasons'])} · {c['owner_team']}/{c['owner']}")
            made.append({"ticket_id": tid, "title": title, "channel": c["slack_channel"], "owner": c["owner"]})
    return made


def track(store, log_date):
    """그날 평균으로 열린 · 해결된 티켓의 상태를 갱신. 바뀐 (ticket_id, 이전, 이후) 목록을 돌려준다."""
    changed = []
    with store.cursor() as cur:
        cur.execute("""SELECT t.ticket_id, t.status, t.baseline_avg_sec, d.avg_sec
                       FROM tuning_ticket t LEFT JOIN slow_digest_daily d
                         ON d.cluster=t.cluster AND d.qhash=t.qhash AND d.log_date=%s""", (log_date,))
        for r in cur.fetchall():
            new = next_status(r["status"], r["baseline_avg_sec"], r["avg_sec"])
            if new == r["status"]:
                continue
            at = f"{log_date} 09:00:00"
            if new == "RESOLVED":
                cur.execute("UPDATE tuning_ticket SET status=%s, after_avg_sec=%s, resolved_at=%s WHERE ticket_id=%s",
                            (new, r["avg_sec"], at, r["ticket_id"]))
            else:
                cur.execute("UPDATE tuning_ticket SET status=%s WHERE ticket_id=%s", (new, r["ticket_id"]))
            _event(cur, r["ticket_id"], at, new, f"{r['baseline_avg_sec']:.3f}s → {r['avg_sec']:.4f}s")
            changed.append((r["ticket_id"], r["status"], new))
    return changed
