"""Publish 단계: 새 티켓을 Jira 이슈 · Slack 메시지로 내보낸다. 기본은 dry-run(보내지 않고 본문만 로그).

실제 전송 조건 (둘 다 만족해야 함)
  1) 환경 변수 PUBLISH_DRY_RUN=false   (Terraform 변수 publish_dry_run)
  2) 발행 비밀(PUBLISH_SECRET_ARN)에 해당 채널 자격 증명이 있음
     {"jira_base_url", "jira_email", "jira_api_token", "jira_project_key", "jira_issue_type", "jira_api_version": "2"|"3",
      "slack_bot_token" 또는 "slack_webhook_url"}
- 토큰 · 웹훅 주소는 어떤 로그에도 남기지 않는다 (redact 로 한 번 더 가린다).
- Jira 성공 즉시 ticket_event 'PUBLISHED' 를 남겨, 다시 실행해도 같은 티켓을 두 번 만들지 않는다.
- Lambda 가 VPC 안에 있으므로 실제 전송에는 NAT(enable_nat=true)가 필요하다.
"""
import base64
import json
import urllib.error
import urllib.request

from . import common

HTTP_TIMEOUT = 10
LOOKBACK_DAYS = 7

TARGET_SQL = """
SELECT t.ticket_id, t.cluster, t.qhash, t.title, t.status, t.owner, t.baseline_avg_sec, t.recommendation,
       c.owner_team, c.slack_channel,
       (SELECT d.query_text FROM slow_digest_daily d WHERE d.cluster=t.cluster AND d.qhash=t.qhash
         ORDER BY d.log_date DESC LIMIT 1) AS query_text
FROM tuning_ticket t JOIN cmdb_cluster c ON c.cluster = t.cluster
WHERE t.created_at >= %s - INTERVAL %s DAY
  AND NOT EXISTS (SELECT 1 FROM ticket_event e WHERE e.ticket_id = t.ticket_id AND e.event = 'PUBLISHED')
ORDER BY t.ticket_id
LIMIT %s
"""


class PublishError(RuntimeError):
    pass


def _basic(cfg):
    return base64.b64encode(f"{cfg.get('jira_email', '')}:{cfg.get('jira_api_token', '')}".encode()).decode()


def redact(text, secret):
    """비밀 값(과 그것으로 만든 Basic 인증 값)이 문자열에 섞여 있으면 *** 로 바꾼다."""
    out = str(text)
    values = [v for v in (secret or {}).values() if isinstance(v, str)]
    if (secret or {}).get("jira_api_token"):
        values.append(_basic(secret))
    for v in sorted(values, key=len, reverse=True):
        if len(v) >= 6 and v in out:
            out = out.replace(v, "***")
    return out


def summary_lines(t, dashboard_url):
    rec = json.loads(t.get("recommendation") or "{}")
    v = rec.get("verify") or {}
    link = f"{dashboard_url}?var-qhash={t['qhash']}" if dashboard_url else "(대시보드 주소 미설정)"
    verify_line = ("실측 검증: " + ("통과" if v.get("pass") else "탈락 · 사람 검토")
                   + (f" ({v.get('before_sec'):.4f}s → {v.get('after_sec'):.4f}s)" if v.get("before_sec") is not None
                      and v.get("after_sec") is not None else "")) if v else "실측 검증: 없음"
    return [f"쿼리(마스킹): {(t.get('query_text') or '(없음)')[:1000]}",
            f"기준: 평균 {float(t['baseline_avg_sec']):.2f}s · 담당 {t['owner_team']}/{t['owner']}",
            f"원인(AI): {rec.get('cause', '분석 전')}",
            "근거: " + " / ".join((rec.get("evidence") or [])[:2]),
            f"제안: {rec.get('proposal', '-')}",
            verify_line,
            "운영 반영은 apply_plan 으로 변경 계획을 만든 뒤 사람이 승인해 진행합니다.",
            f"대시보드: {link}"]


def jira_body(t, cfg, dashboard_url):
    lines = summary_lines(t, dashboard_url)
    fields = {"project": {"key": cfg.get("jira_project_key", "SLOWQ")},
              "issuetype": {"name": cfg.get("jira_issue_type", "Task")},
              "summary": t["title"][:250],
              "labels": ["slow-query", t["cluster"], f"qhash-{t['qhash'][:8]}"]}
    if str(cfg.get("jira_api_version", "3")) == "2":
        fields["description"] = "\n".join(lines)                     # v2: 일반 문자열
    else:                                                             # v3: Atlassian Document Format
        fields["description"] = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": ln}]} for ln in lines if ln]}
    return {"fields": fields}


def slack_body(t, channel, dashboard_url):
    rec = json.loads(t.get("recommendation") or "{}")
    link = f"{dashboard_url}?var-qhash={t['qhash']}" if dashboard_url else "-"
    return {"channel": channel,
            "text": f"[{t['status']}] {t['title']} → {t['owner_team']} {t['owner']}\n"
                    f"제안: {rec.get('proposal', '분석 전')}\n대시보드: {link}"}


def http_post(url, body, headers, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers=dict(headers, **{"Content-Type": "application/json; charset=utf-8"}))
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — https 주소만 허용(아래 검사)
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw[:200]}


def _https(url):
    if not isinstance(url, str) or not url.startswith("https://"):
        raise PublishError("https 주소만 허용합니다")
    return url.rstrip("/")


def send_jira(body, cfg, post=http_post):
    ver = "2" if str(cfg.get("jira_api_version", "3")) == "2" else "3"
    auth = _basic(cfg)
    r = post(f"{_https(cfg['jira_base_url'])}/rest/api/{ver}/issue", body,
             {"Authorization": f"Basic {auth}", "Accept": "application/json"})
    if not r.get("key"):
        raise PublishError(f"Jira 응답에 key 가 없습니다: {str(r)[:200]}")
    return r["key"]


def send_slack(body, cfg, post=http_post):
    if cfg.get("slack_bot_token"):
        r = post("https://slack.com/api/chat.postMessage", body,
                 {"Authorization": f"Bearer {cfg['slack_bot_token']}"})
        if not r.get("ok"):
            raise PublishError(f"Slack 오류: {r.get('error', 'unknown')}")
        return "chat.postMessage"
    post(_https(cfg["slack_webhook_url"]), {"text": body["text"]}, {})
    return "webhook"


def channels(cfg, dry_run):
    """실제로 보낼 채널. dry-run 이면 빈 집합."""
    if dry_run:
        return set()
    ch = set()
    if all(cfg.get(k) for k in ("jira_base_url", "jira_email", "jira_api_token", "jira_project_key")):
        ch.add("jira")
    if cfg.get("slack_bot_token") or cfg.get("slack_webhook_url"):
        ch.add("slack")
    return ch


def publish(store, log_date, cfg, dry_run, dashboard_url, limit=20, post=http_post):
    live = channels(cfg, dry_run)
    with store.cursor() as cur:
        cur.execute(TARGET_SQL, (log_date, LOOKBACK_DAYS, int(limit)))
        targets = cur.fetchall()
    out = {"mode": "live:" + ",".join(sorted(live)) if live else "dry-run", "sent": [], "previewed": [], "errors": []}
    for t in targets:
        jb, sb = jira_body(t, cfg, dashboard_url), slack_body(t, t["slack_channel"], dashboard_url)
        if not live:
            common.log.info("# dry-run (보내지 않음) jira=%s", json.dumps(jb, ensure_ascii=False)[:2000])
            common.log.info("# dry-run (보내지 않음) slack=%s", json.dumps(sb, ensure_ascii=False))
            out["previewed"].append(t["ticket_id"])
            continue
        note = []
        try:
            if "jira" in live:
                note.append("jira " + send_jira(jb, cfg, post))
            if "slack" in live:
                try:
                    note.append("slack " + send_slack(sb, cfg, post))
                except Exception as e:  # noqa: BLE001 — 알림 실패는 기록만 (이슈는 이미 만들어졌으므로 재시도하지 않음)
                    common.log.warning("Slack 전송 실패 ticket=%s: %s", t["ticket_id"], redact(e, cfg))
                    note.append("slack 실패")
        except Exception as e:  # noqa: BLE001 — 티켓 단위 격리, 끝에서 한꺼번에 실패로 알린다
            msg = redact(f"{type(e).__name__}: {e}", cfg)[:300]
            common.log.error("발행 실패 ticket=%s: %s", t["ticket_id"], msg)
            out["errors"].append({"ticket_id": t["ticket_id"], "error": msg})
            continue
        with store.cursor() as cur:
            cur.execute("INSERT INTO ticket_event (ticket_id, at, event, note) VALUES (%s, NOW(), 'PUBLISHED', %s)",
                        (t["ticket_id"], " · ".join(note)[:500]))
        out["sent"].append(t["ticket_id"])
    return out


def handler(event, context):
    log_date = common.resolve_log_date(event)
    dry_run = common.env("PUBLISH_DRY_RUN", "true").lower() != "false"
    cfg = common.get_secret(common.env("PUBLISH_SECRET_ARN")) if not dry_run else {}
    store = common.store_conn()
    try:
        out = publish(store, log_date, cfg, dry_run, common.env("DASHBOARD_URL", ""), int(common.env("PUBLISH_MAX", "20")))
    finally:
        store.close()
    if out["errors"]:
        raise PublishError(f"발행 실패 {len(out['errors'])}건: {out['errors']}")
    return out
