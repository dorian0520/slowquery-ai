"""Publish: 기본 dry-run, 실제 전송은 비밀이 있을 때만, 토큰은 로그에 남지 않는다."""
import json
import logging

import pytest

from slowq_aws import common
from slowq_aws import publish as P

TOKEN = "jira-token-SHOULD-NOT-LEAK-123"
SLACK = "xoxb-slack-SHOULD-NOT-LEAK-456"
CFG = {"jira_base_url": "https://example.atlassian.net", "jira_email": "bot@example.com", "jira_api_token": TOKEN,
       "jira_project_key": "SLOWQ", "jira_api_version": "3", "slack_bot_token": SLACK}
TICKET = {"ticket_id": 1, "cluster": "shop-db", "qhash": "5e9245c3092ff8032ccbe00d8fa31da9",
          "title": "[슬로우쿼리] shop-db 5e9245c3 평균 0.27s × 44회", "status": "OPEN", "owner": "dev-kim",
          "baseline_avg_sec": 0.27, "owner_team": "주문개발팀", "slack_channel": "#shop-db-alert",
          "query_text": "SELECT * FROM orders WHERE user_id = ?",
          "recommendation": json.dumps({"cause": "인덱스 없음", "evidence": ["rows=2e6"], "proposal": "ALTER TABLE ...",
                                        "verify": {"pass": True, "before_sec": 0.27, "after_sec": 0.0002}})}


def store(fake_conn):
    return fake_conn(rules=[(r"FROM tuning_ticket t JOIN cmdb_cluster", [TICKET])])


def no_post(*a, **k):
    raise AssertionError("dry-run 에서 HTTP 를 보내면 안 됩니다")


def test_dry_run_sends_nothing_and_records_no_event(fake_conn):
    s = store(fake_conn)
    out = P.publish(s, "2026-10-12", CFG, dry_run=True, dashboard_url="", post=no_post)
    assert out["mode"] == "dry-run" and out["previewed"] == [1] and out["sent"] == []
    assert not any("INSERT INTO ticket_event" in q for q in s.sqls())


def test_live_without_credentials_is_still_dry_run(fake_conn):
    out = P.publish(store(fake_conn), "2026-10-12", {}, dry_run=False, dashboard_url="", post=no_post)
    assert out["mode"] == "dry-run"


def test_handler_default_is_dry_run_and_reads_no_secret(fake_conn, monkeypatch):
    monkeypatch.delenv("PUBLISH_DRY_RUN", raising=False)
    monkeypatch.setattr(common, "get_secret", lambda arn: pytest.fail("dry-run 에서 비밀을 읽으면 안 됩니다"))
    monkeypatch.setattr(common, "store_conn", lambda: store(fake_conn))
    monkeypatch.setattr(P, "http_post", no_post)
    assert P.handler({"log_date": "2026-10-12"}, None)["mode"] == "dry-run"


def test_live_send_jira_v3_and_slack(fake_conn):
    calls = []

    def post(url, body, headers, timeout=10):
        calls.append((url, body, headers))
        return {"key": "SLOWQ-1"} if "/rest/api/" in url else {"ok": True}
    s = store(fake_conn)
    out = P.publish(s, "2026-10-12", CFG, dry_run=False, dashboard_url="https://grafana.example/d/x", post=post)
    assert out["sent"] == [1] and out["mode"] == "live:jira,slack"
    assert calls[0][0] == "https://example.atlassian.net/rest/api/3/issue"
    assert calls[0][1]["fields"]["description"]["type"] == "doc"           # v3 = ADF
    assert calls[1][0] == "https://slack.com/api/chat.postMessage" and calls[1][1]["channel"] == "#shop-db-alert"
    assert any("'PUBLISHED'" in q for q in s.sqls())


def test_jira_v2_plain_description():
    b = P.jira_body(TICKET, dict(CFG, jira_api_version="2"), "")
    assert isinstance(b["fields"]["description"], str) and "인덱스 없음" in b["fields"]["description"]


def test_tokens_never_logged_on_failure(fake_conn, caplog):
    def post(url, body, headers, timeout=10):
        raise RuntimeError(f"connection reset while sending {headers}")          # 헤더(토큰)가 예외 문구에 섞이는 최악의 경우
    caplog.set_level(logging.DEBUG, logger="slowq")
    out = P.publish(store(fake_conn), "2026-10-12", CFG, dry_run=False, dashboard_url="", post=post)
    assert out["errors"] and out["sent"] == []
    import base64
    basic = base64.b64encode(f"bot@example.com:{TOKEN}".encode()).decode()
    joined = caplog.text + json.dumps(out, ensure_ascii=False)
    assert TOKEN not in joined and SLACK not in joined and basic not in joined


def test_handler_raises_when_any_ticket_failed(fake_conn, monkeypatch):
    monkeypatch.setenv("PUBLISH_DRY_RUN", "false")
    monkeypatch.setenv("PUBLISH_SECRET_ARN", "dummy")
    monkeypatch.setattr(common, "get_secret", lambda arn: CFG)
    monkeypatch.setattr(common, "store_conn", lambda: store(fake_conn))
    monkeypatch.setattr(P, "http_post", lambda *a, **k: {"errorMessages": ["no"]})
    with pytest.raises(P.PublishError) as e:
        P.handler({"log_date": "2026-10-12"}, None)
    assert TOKEN not in str(e.value)


def test_non_https_jira_url_rejected():
    with pytest.raises(P.PublishError):
        P.send_jira({}, dict(CFG, jira_base_url="http://plain.example"), post=no_post)
