"""Analyze: Bedrock Converse 도구 루프와 엄격한 JSON 파싱 (Bedrock 은 가짜 클라이언트)."""
import json

from slowq_aws import analyze as A
from slowq_aws.tools import Tools

QH = "5e9245c3092ff8032ccbe00d8fa31da9"
ITEM = {"ticket_id": 7, "cluster": "shop-db", "qhash": QH, "log_date": "2026-10-12",
        "query_text": "SELECT * FROM users WHERE email = 'kim@example.com' AND user_id = 42"}
GOOD = [{"qhash": QH, "cause": "user_id 인덱스 없음", "evidence": ["Table scan rows=1.99e+6"],
         "proposal": "ALTER TABLE orders ADD INDEX ix_u (user_id, ordered_at);", "expected": "(예상) 수십 행",
         "confidence": "high", "verify": "전후 비교", "test_sql": "SELECT order_id FROM orders WHERE user_id = 1001"}]


def text_resp(text):
    return {"stopReason": "end_turn", "usage": {"inputTokens": 10, "outputTokens": 5},
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}}}


def tool_resp(name, inp, tid="t1"):
    return {"stopReason": "tool_use", "usage": {"inputTokens": 10, "outputTokens": 5},
            "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": inp}}]}}}


class FakeBedrock:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def converse(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=str)))
        return self.responses.pop(0)


def tools(fake_conn, shop=None):
    shop = shop or fake_conn(rules=[(r"^EXPLAIN", [{"EXPLAIN": "-> Table scan on orders (rows=1.99e+6)"}])])
    return Tools(fake_conn(), shop, "shop-db"), shop


def test_tool_loop_then_valid_json(fake_conn):
    t, shop = tools(fake_conn)
    bed = FakeBedrock([tool_resp("explain", {"sql": "SELECT * FROM orders WHERE user_id = 1"}),
                       text_resp("```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```")])
    r = A.analyze(ITEM, bed, t, "model-x")
    assert r["status"] == "OK" and r["proposal"]["test_sql"].startswith("SELECT")
    assert any(s.startswith("EXPLAIN FORMAT=TREE SELECT") for s in shop.sqls())
    assert r["usage"]["tool_calls"] == 1 and r["usage"]["turns"] == 2
    tool_result = bed.calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert tool_result["status"] == "success" and "Table scan" in tool_result["content"][0]["text"]


def test_query_values_are_masked_before_model(fake_conn):
    t, _ = tools(fake_conn)
    bed = FakeBedrock([text_resp(json.dumps(GOOD))])
    A.analyze(ITEM, bed, t, "model-x")
    sent = json.dumps(bed.calls[0]["messages"], ensure_ascii=False)
    assert "kim@example.com" not in sent and "= 42" not in sent


def test_broken_json_is_format_error_not_exception(fake_conn):
    t, _ = tools(fake_conn)
    r = A.analyze(ITEM, FakeBedrock([text_resp('[{"qhash": "a", "proposal": "x"]')]), t, "model-x")
    assert r["status"] == "FORMAT_ERROR" and r["proposal"] is None


def test_missing_test_sql_is_format_error(fake_conn):
    bad = [dict(GOOD[0])]
    del bad[0]["test_sql"]
    t, _ = tools(fake_conn)
    r = A.analyze(ITEM, FakeBedrock([text_resp(json.dumps(bad))]), t, "model-x")
    assert r["status"] == "FORMAT_ERROR" and "test_sql" in r["error"]


def test_other_qhash_only_is_format_error(fake_conn):
    other = [dict(GOOD[0], qhash="ffff")]
    t, _ = tools(fake_conn)
    assert A.analyze(ITEM, FakeBedrock([text_resp(json.dumps(other))]), t, "m")["status"] == "FORMAT_ERROR"


def test_bad_confidence_is_format_error(fake_conn):
    t, _ = tools(fake_conn)
    bad = [dict(GOOD[0], confidence="certain")]
    assert A.analyze(ITEM, FakeBedrock([text_resp(json.dumps(bad))]), t, "m")["status"] == "FORMAT_ERROR"


def test_turn_limit_gives_no_answer(fake_conn):
    t, _ = tools(fake_conn)
    bed = FakeBedrock([tool_resp("query_trend", {"qhash": QH}, tid=f"t{i}") for i in range(3)])
    r = A.analyze(ITEM, bed, t, "m", max_turns=3)
    assert r["status"] == "NO_ANSWER" and len(bed.calls) == 3


def test_rejected_tool_sql_is_reported_as_error_to_model(fake_conn):
    t, shop = tools(fake_conn)
    bed = FakeBedrock([tool_resp("explain", {"sql": "DROP TABLE orders"}), text_resp(json.dumps(GOOD))])
    A.analyze(ITEM, bed, t, "m")
    tr = bed.calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert tr["status"] == "error" and shop.executed == []


def test_request_shape(fake_conn):
    t, _ = tools(fake_conn)
    bed = FakeBedrock([text_resp(json.dumps(GOOD))])
    A.analyze(ITEM, bed, t, "global.example-model", max_tokens=1000)
    c = bed.calls[0]
    assert c["modelId"] == "global.example-model"
    assert {s["toolSpec"]["name"] for s in c["toolConfig"]["tools"]} == {"top_queries", "table_info", "explain", "query_trend"}
    assert c["inferenceConfig"] == {"maxTokens": 1000, "temperature": 0}
    assert "JSON" in c["system"][0]["text"]
