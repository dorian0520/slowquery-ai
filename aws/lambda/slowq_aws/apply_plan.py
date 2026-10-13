"""apply_plan (수동 실행): 실측 검증을 통과한 제안으로 운영 반영 '계획서'만 만든다. 운영 DDL 은 실행하지 않는다.

aws lambda invoke --function-name <prefix>-apply-plan --payload '{"ticket_id": 1}' out.json

- 계획서(Markdown)를 S3 plans/ 에 올리고 ticket_event 에 PLAN_CREATED 를 남긴다.
- 반영은 사람이 승인한 뒤, 계획서의 사전 점검 → 온라인 DDL → 사후 확인 순서로 직접 실행한다 (README 「운영 반영」).
- 이 Lambda 의 DB 계정은 읽기 전용(slowq_ai)이고, 저장소 쓰기는 이벤트 기록뿐이다.
"""
import json
import re

from slowq.verify import index_target

from . import common

CAN_APPLY = ("OPEN", "IN_PROGRESS", "REOPENED")
LONG_TRX_SEC = 10
LOCK_WAIT_SEC = 5


class PlanError(ValueError):
    """자동으로 계획을 만들 수 없는 경우 — 사람이 판단한다."""


def build_plan(ticket):
    if ticket["status"] not in CAN_APPLY:
        raise PlanError(f"티켓 상태가 {ticket['status']} 입니다 → 계획을 만들지 않습니다")
    rec = json.loads(ticket.get("recommendation") or "null")
    if not rec or rec.get("status") != "OK":
        raise PlanError("AI 분석 결과가 없거나 형식 오류입니다 → 먼저 분석 · 실측 검증을 거칩니다")
    v = rec.get("verify") or {}
    if not v.get("pass"):
        raise PlanError("실측 검증을 통과하지 않은 제안입니다 → 계획을 만들지 않습니다")
    t = index_target(v.get("ddl") or "")
    if not t:
        raise PlanError("ADD INDEX 한 절 형식이 아닙니다 → 사람이 검토합니다")
    table, index, _ = t
    cols = re.search(r"\(([^()]*)\)\s*$", t[2]).group(1)
    return {"table": table, "index": index, "cols": cols,
            "apply": f"ALTER TABLE {table} ADD INDEX {index} ({cols}), ALGORITHM=INPLACE, LOCK=NONE",
            "rollback": f"ALTER TABLE {table} DROP INDEX {index}",
            "evidence": f"{v.get('before_sec')}s → {v.get('after_sec')}s · 결과 동일 {v.get('same')}",
            "test_sql": rec.get("test_sql")}


def find_duplicate(rows, index, cols):
    want = re.sub(r"[\s`]", "", cols).lower()
    for r in rows:
        r = {k.lower(): v for k, v in r.items()}
        if r["index_name"] == index or (r["cols"] or "").lower() == want:
            return r["index_name"]
    return None


def duplicate_of(conn, shop_db, plan):
    table = plan["table"].split(".")[-1].strip("`")
    with conn.cursor() as cur:
        cur.execute("""SELECT index_name AS index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS cols
                       FROM information_schema.statistics WHERE table_schema=%s AND table_name=%s
                       GROUP BY index_name""", (shop_db, table))
        return find_duplicate(cur.fetchall(), plan["index"], plan["cols"])


def render(ticket, plan, dup):
    status = f"반영하지 않음 — 같은 인덱스가 이미 있음 ({dup})" if dup else "승인 대기"
    return "\n".join([
        f"# 변경 계획 — 티켓 #{ticket['ticket_id']} {ticket['title']}", "",
        f"- 상태: **{status}**",
        f"- 대상: {ticket['cluster']} · {plan['table']}",
        f"- 근거(검증 DB 실측): {plan['evidence']}",
        f"- 검증에 쓴 쿼리: `{plan['test_sql']}`", "",
        "## 1. 사전 점검 (사람이 실행)",
        f"- `{LONG_TRX_SEC}`초 넘게 열린 트랜잭션이 없는지: "
        f"`SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_started < NOW() - INTERVAL {LONG_TRX_SEC} SECOND;`",
        "- 테이블 크기와 여유 스토리지 확인 (인덱스 크기만큼 필요)",
        "- 같은 컬럼 조합 인덱스가 없는지 (이 계획서 생성 시 자동 확인함)", "",
        "## 2. 반영 (온라인 DDL)",
        f"```sql\nSET SESSION lock_wait_timeout = {LOCK_WAIT_SEC};\n{plan['apply']};\n```", "",
        "## 3. 되돌리기",
        f"```sql\n{plan['rollback']};\n```", "",
        "## 4. 사후 확인",
        "- 검증에 쓴 쿼리의 EXPLAIN 에서 새 인덱스를 쓰는지 확인",
        "- 다음 날 Track 단계에서 기준의 절반 이하로 내려가 RESOLVED 가 되는지 확인", "",
        "## 승인",
        "- [ ] 서비스 담당 확인   - [ ] DBA 확인   - [ ] 반영 시간대 합의", ""])


def handler(event, context, s3=None):
    tid = int(event["ticket_id"])
    store = common.store_conn()
    try:
        with store.cursor() as cur:
            cur.execute("SELECT * FROM tuning_ticket WHERE ticket_id=%s", (tid,))
            ticket = cur.fetchone()
        if not ticket:
            raise PlanError(f"티켓 #{tid} 이 없습니다")
        plan = build_plan(ticket)
        shop_db = common.env("SHOP_DB", "shop")
        ro = common.connect(common.env("TARGET_HOST", required=True), common.env("AI_SECRET_ARN", required=True), shop_db)
        try:
            dup = duplicate_of(ro, shop_db, plan)
        finally:
            ro.close()
        md = render(ticket, plan, dup)
        if s3 is None:
            import boto3
            s3 = boto3.client("s3")
        key = f"plans/ticket-{tid}.md"
        s3.put_object(Bucket=common.env("REPORT_BUCKET", required=True), Key=key, Body=md.encode("utf-8"),
                      ContentType="text/markdown; charset=utf-8")
        with store.cursor() as cur:
            cur.execute("INSERT INTO ticket_event (ticket_id, at, event, note) VALUES (%s, NOW(), 'PLAN_CREATED', %s)",
                        (tid, f"s3 {key} · {'중복 인덱스' if dup else '승인 대기'}"))
    finally:
        store.close()
    return {"ticket_id": tid, "plan": key, "duplicate": dup, "executed": False}
