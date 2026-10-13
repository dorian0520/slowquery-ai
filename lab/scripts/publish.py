"""섹션 6: AI 분석 · 실측 검증 결과를 티켓에 붙이고, 외부 발행 내용을 미리 본다(dry-run).

python3 publish.py attach ../ai/run1.txt ../ai/verify_run1.txt --log-date 2026-10-12
python3 publish.py payload 1 --to jira     # Jira 이슈 생성 요청 본문 (보내지 않고 출력만)
python3 publish.py payload 1 --to slack    # Slack 알림 본문 (보내지 않고 출력만)
"""
import argparse, json, re
from common import STORE, connect

DASHBOARD = "http://localhost:3000/d/lab-slowquery?var-qhash={qhash}"


def parse_verify(path):
    """verify.py 출력 → {qhash 앞 8자리: {"pass": bool, "line": 시간 줄}}"""
    out, cur = {}, None
    for line in open(path):
        m = re.match(r"\[(\w{8})\] (통과|탈락)", line)
        if m:
            cur = m.group(1); out[cur] = {"pass": m.group(2) == "통과"}
        elif cur and line.strip().startswith("시간"):
            out[cur]["line"] = line.strip()
    return out


def attach(run_path, verify_path, log_date):
    text = open(run_path).read()
    proposals = json.loads(text[text.index("["): text.rindex("]") + 1])
    checked = parse_verify(verify_path)
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        for p in proposals:
            v = checked.get(p["qhash"][:8])
            cur.execute("SELECT ticket_id FROM tuning_ticket WHERE cluster='shop-db' AND qhash=%s", (p["qhash"],))
            t = cur.fetchone()
            if not t:
                print(f"[{p['qhash'][:8]}] 티켓 없음 (발행 기준 미달) — 붙이지 않음"); continue
            rec = {"cause": p["cause"], "evidence": p["evidence"], "proposal": p["proposal"],
                   "confidence": p["confidence"], "verify": v}
            cur.execute("UPDATE tuning_ticket SET recommendation=%s WHERE ticket_id=%s",
                        (json.dumps(rec, ensure_ascii=False), t["ticket_id"]))
            result = "검증 없음" if not v else ("실측 통과" if v["pass"] else "실측 탈락 → 사람 검토")
            cur.execute("""INSERT INTO ticket_event (ticket_id, at, event, note)
                           SELECT %s, %s, 'AI_ANALYZED', %s FROM DUAL WHERE NOT EXISTS (      -- 다시 실행해도 이벤트는 한 번
                             SELECT 1 FROM ticket_event WHERE ticket_id=%s AND event='AI_ANALYZED' AND at=%s)""",
                        (t["ticket_id"], f"{log_date} 10:00:00", f"{p['confidence']} · {result}", t["ticket_id"], f"{log_date} 10:00:00"))
            print(f"#{t['ticket_id']} [{p['qhash'][:8]}] {result}")


def payload(ticket_id, to):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute("""SELECT t.*, c.owner_team, c.slack_channel FROM tuning_ticket t
                       JOIN cmdb_cluster c ON c.cluster = t.cluster WHERE t.ticket_id=%s""", (ticket_id,))
        t = cur.fetchone()
        if not t:
            raise SystemExit(f"티켓 #{ticket_id} 이 없습니다")
        cur.execute("SELECT query_text FROM slow_digest_daily WHERE cluster=%s AND qhash=%s LIMIT 1", (t["cluster"], t["qhash"]))
        q = cur.fetchone()
        sql = q["query_text"] if q else "(수집된 쿼리 원문 없음)"
    rec = json.loads(t["recommendation"] or "{}")
    v = rec.get("verify") or {}
    link = DASHBOARD.format(qhash=t["qhash"])
    if to == "jira":
        body = {"fields": {
            "project": {"key": "DBTUNE"}, "issuetype": {"name": "Task"},
            "summary": t["title"],
            "labels": ["slow-query", t["cluster"], f"qhash-{t['qhash'][:8]}"],   # 같은 지문 중복 검색용
            "assignee": {"name": t["owner"]},
            "description": "\n".join([
                f"쿼리(마스킹): {sql}",
                f"기준: 평균 {t['baseline_avg_sec']:.2f}s · 담당 {t['owner_team']}",
                f"원인(AI): {rec.get('cause', '분석 전')}",
                "근거: " + " / ".join(rec.get("evidence", [])[:2]),
                f"제안: {rec.get('proposal', '-')}",
                f"실측 검증: {'통과' if v.get('pass') else '탈락 · 사람 검토'} — {v.get('line', '-')}" if v else "실측 검증: 없음",
                f"대시보드: {link}"])}}
    else:
        body = {"channel": t["slack_channel"],
                "text": f"[{t['status']}] {t['title']} → {t['owner_team']} {t['owner']}\n"
                        f"제안: {rec.get('proposal', '분석 전')}\n대시보드: {link}"}
    print(f"# dry-run: {to} 로 보낼 내용 (실제로 보내지 않음)")
    print(json.dumps(body, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("attach"); a.add_argument("run"); a.add_argument("verify"); a.add_argument("--log-date", required=True)
    b = sub.add_parser("payload"); b.add_argument("ticket_id", type=int); b.add_argument("--to", choices=["jira", "slack"], default="jira")
    x = ap.parse_args()
    attach(x.run, x.verify, x.log_date) if x.cmd == "attach" else payload(x.ticket_id, x.to)
