"""섹션 9 · 운영 반영: 실측 검증을 통과한 제안만 변경 계획으로 만들고, 온라인 DDL 로 반영한다.

python3 apply_fix.py plan  --ticket 1                       # 변경 계획만 출력 (아무것도 바꾸지 않음)
python3 apply_fix.py apply --ticket 1 --log-date 2026-10-13 # 반영 + 반영 중 조회 지연 측정 + 사후 확인 + 이벤트 기록
"""
import argparse, json, re, statistics, threading, time
from common import STORE, connect

IDX = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+INDEX\s+(\w+)\s*(\([^)]*\))", re.I)


class PlanError(ValueError):
    """자동 반영 계획을 만들 수 없는 경우 — 사람이 판단한다."""


def build_plan(rec):
    if not rec:
        raise PlanError("AI 분석 · 검증 결과가 없습니다 → 먼저 분석과 실측 검증을 거칩니다")
    v = rec.get("verify") or {}
    if not v.get("pass"):
        raise PlanError("실측 검증을 통과하지 않은 제안입니다 → 반영 계획을 만들지 않습니다")
    m = IDX.search(rec.get("proposal", ""))
    if not m:
        raise PlanError("ADD INDEX 형식의 제안이 아닙니다 → 사람이 검토합니다")
    table, idx, cols = m.groups()
    return {"table": table, "index": idx,
            "apply": f"ALTER TABLE {table} ADD INDEX {idx} {cols}, ALGORITHM=INPLACE, LOCK=NONE",   # 쓰기를 막지 않는 온라인 DDL
            "rollback": f"ALTER TABLE {table} DROP INDEX {idx}",
            "evidence": v.get("line", "")}


LONG_TRX_SEC = 10      # 이보다 오래 열린 트랜잭션이 있으면 반영하지 않는다
LOCK_WAIT_SEC = 5      # 메타데이터 락을 이보다 오래 기다리면 DDL 을 취소한다


def can_apply(status):
    """이미 해결된 티켓에는 다시 반영하지 않는다."""
    return status in ("OPEN", "IN_PROGRESS", "REOPENED")


def find_duplicate(rows, index, cols):
    """이름이 같거나 컬럼 조합이 같은 인덱스가 있으면 그 이름. information_schema 는 열 이름을 대문자로 돌려줄 수 있다."""
    for r in rows:
        r = {k.lower(): v for k, v in r.items()}
        if r["index_name"] == index or r["cols"] == cols:
            return r["index_name"]
    return None


def precheck(long_trx):
    """온라인 DDL 도 시작 · 끝에 메타데이터 락을 잠깐 잡는다. 긴 트랜잭션이 있으면 DDL 이 대기하고 뒤의 조회가 줄줄이 막힌다."""
    if long_trx:
        return {"ok": False, "reason": f"{LONG_TRX_SEC}초 넘게 열린 트랜잭션 {long_trx}건 → 끝난 뒤 반영합니다"}
    return {"ok": True, "reason": ""}


def server_state(cur, table):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.innodb_trx "
                "WHERE trx_started < NOW() - INTERVAL %s SECOND", (LONG_TRX_SEC,))
    n = cur.fetchone()["n"]
    cur.execute("SELECT ROUND((data_length + index_length) / 1024 / 1024) AS mb FROM information_schema.tables "
                "WHERE table_schema = 'shop' AND table_name = %s", (table,))
    return n, cur.fetchone()["mb"]


def duplicate_of(cur, p):
    cur.execute("""SELECT index_name AS index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS cols
                   FROM information_schema.statistics WHERE table_schema='shop' AND table_name=%s
                   GROUP BY index_name""", (p["table"],))
    want = re.sub(r"\s", "", re.search(r"\(([^)]*)\)", p["apply"]).group(1))
    return find_duplicate(cur.fetchall(), p["index"], want)   # 이름이 달라도 같은 컬럼 조합이면 중복


def load(ticket_id):
    with connect(STORE, db="dba") as db, db.cursor() as cur:
        cur.execute("SELECT * FROM tuning_ticket WHERE ticket_id=%s", (ticket_id,))
        return cur.fetchone()


def show_plan(t, p):
    print(f"# 변경 계획 — 티켓 #{t['ticket_id']} {t['title']}")
    print(f"대상      : {t['cluster']} · {p['table']}")
    print(f"근거      : 실측 검증 통과 — {p['evidence']}")
    print(f"반영 DDL  : {p['apply']};")
    print(f"되돌리기  : {p['rollback']};")
    print("사후 확인 : EXPLAIN 에서 새 인덱스 사용 · 다음 날 추적에서 기준의 절반 이하")
    with connect(t["cluster"], user="root", password="lab-root-pw", db="shop") as c, c.cursor() as cur:
        n, mb = server_state(cur, p["table"])
        dup = duplicate_of(cur, p)
    pc = precheck(n)
    if not can_apply(t["status"]):
        pc = {"ok": False, "reason": f"티켓 상태가 {t['status']} 입니다 → 반영하지 않습니다"}
    elif dup:
        pc = {"ok": False, "reason": f"이미 같은 인덱스가 있습니다 ({dup}) → 반영하지 않습니다"}
    print(f"사전 점검 : 테이블 약 {mb} MB · {LONG_TRX_SEC}초 넘게 열린 트랜잭션 {n}건 · "
          f"메타데이터 락 대기 {LOCK_WAIT_SEC}초 넘으면 취소 → {'반영 가능' if pc['ok'] else pc['reason']}")
    return pc


def apply(t, p, log_date):
    if not can_apply(t["status"]):
        raise PlanError(f"티켓 상태가 {t['status']} 입니다 → 반영하지 않습니다")
    conn = connect(t["cluster"], user="root", password="lab-root-pw", db="shop")
    try:
        _apply(conn, conn.cursor(), t, p, log_date)
    finally:
        conn.close()


def _apply(conn, cur, t, p, log_date):
    dup = duplicate_of(cur, p)
    if dup:
        raise PlanError(f"이미 같은 인덱스가 있습니다 ({dup}) → 반영하지 않습니다")
    lat, stop = [], threading.Event()

    def reader():   # 반영하는 동안 다른 세션의 조회가 막히는지 잰다
        with connect(t["cluster"], user="root", password="lab-root-pw", db="shop") as c2, c2.cursor() as c:
            i = 0
            while not stop.is_set():
                s = time.perf_counter(); c.execute("SELECT amount FROM orders WHERE order_id=%s", (1000 + i % 5000,)); c.fetchall()
                lat.append(time.perf_counter() - s); i += 1
    pc = precheck(server_state(cur, p["table"])[0])
    if not pc["ok"]:
        raise PlanError(pc["reason"])
    cur.execute(f"SET SESSION lock_wait_timeout = {LOCK_WAIT_SEC}")   # 오래 기다리며 뒤의 조회를 막느니 취소한다
    th = threading.Thread(target=reader); th.start(); time.sleep(0.3)
    try:
        s = time.perf_counter(); cur.execute(p["apply"]); ddl_sec = time.perf_counter() - s
        time.sleep(0.3)
    finally:                                   # DDL 이 실패해도 측정 스레드를 멈추고 오류를 그대로 알린다
        stop.set(); th.join()
    print(f"반영 완료 : {ddl_sec:.2f}초")
    if lat:
        print(f"반영 중 조회 {len(lat)}회 · 중앙값 {statistics.median(lat) * 1000:.2f} ms · 최대 {max(lat) * 1000:.2f} ms")
    else:   # 인덱스는 이미 들어갔으므로 기록은 계속한다
        print("경고: 반영 중 조회 측정에 실패했습니다 (측정 세션 접속 확인) — 반영 기록은 계속합니다")
    cur.execute("EXPLAIN FORMAT=TREE SELECT order_id, amount, status, ordered_at FROM orders "
                "WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20")
    print("사후 확인 :", cur.fetchone()["EXPLAIN"].splitlines()[-1].strip()[:110])
    with connect(STORE, db="dba") as db, db.cursor() as c:
        c.execute("UPDATE tuning_ticket SET status='IN_PROGRESS' WHERE ticket_id=%s", (t["ticket_id"],))
        c.execute("INSERT INTO ticket_event (ticket_id, at, event, note) VALUES (%s,%s,'APPLIED',%s)",
                  (t["ticket_id"], f"{log_date} 08:00:00", f"{p['apply']} · {ddl_sec:.2f}s · 되돌리기: {p['rollback']}"))
    print(f"티켓 #{t['ticket_id']} → IN_PROGRESS (다음 날 추적에서 해결 여부를 판정)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "apply"])
    ap.add_argument("--ticket", type=int, required=True)
    ap.add_argument("--log-date")
    a = ap.parse_args()
    t = load(a.ticket)
    if not t:
        raise SystemExit(f"티켓 #{a.ticket} 이 없습니다")
    try:
        p = build_plan(json.loads(t["recommendation"] or "null"))
        pc = show_plan(t, p)
        if a.cmd == "plan" and not pc["ok"]:
            raise SystemExit(2)          # 계획 단계에서도 거부는 종료 코드 2 (apply 와 같게)
        if a.cmd == "apply":
            if not a.log_date:
                ap.error("apply 에는 --log-date 가 필요합니다")
            apply(t, p, a.log_date)
    except PlanError as e:   # 자동 반영 대상이 아님 — 이유를 알리고 멈춘다 (종료 코드 2)
        print(f"티켓 #{a.ticket}: {e}")
        raise SystemExit(2)
