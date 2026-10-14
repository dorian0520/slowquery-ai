"""Analyze 단계: Bedrock Converse API + 근거 도구 4가지로 티켓 하나를 진단한다.

입력 (Map 항목): {"ticket_id", "cluster", "qhash", "query_text", "log_date"}
출력: {"ticket_id", "status": "OK" | "FORMAT_ERROR" | "NO_ANSWER", "proposal": {...} | None, "error": str | None, "usage": {...}}

- 쿼리 원문은 마스킹한 뒤에만 모델에 보낸다.
- 모델 출력은 slowq.analyze.parse_proposals 로 엄격하게 읽고, 형식이 어긋나면 검증 · 발행으로 넘기지 않는다(FORMAT_ERROR).
- 도구 호출 횟수와 출력 토큰에 상한을 둔다(비용 · 폭주 방지).
"""
import json
import os

from slowq.analyze import ProposalFormatError, parse_proposals
from slowq.mask import mask

from . import common
from .tools import SPECS, Tools

PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.md")
CONFIDENCE = ("high", "medium", "low")
TOOL_OUTPUT_LIMIT = 20000          # 도구 결과 한 번에 모델로 보내는 최대 글자 수
MAX_TOOL_CALLS = 16

_bedrock = None


def bedrock_client():
    global _bedrock
    if _bedrock is None:
        import boto3
        from botocore.config import Config
        _bedrock = boto3.client("bedrock-runtime",
                                config=Config(read_timeout=120, connect_timeout=10,
                                              retries={"max_attempts": 4, "mode": "adaptive"}))
    return _bedrock


def system_prompt():
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def validate(proposals, qhash):
    """skeleton 의 필수 키(qhash · proposal) 검사에 더해 AWS 버전 계약(test_sql 등)을 확인하고 해당 지문의 제안 하나를 고른다."""
    mine = [p for p in proposals if p["qhash"] == qhash]
    if len(mine) != 1:
        raise ProposalFormatError(f"qhash {qhash[:8]} 의 제안이 정확히 1개여야 합니다 (받은 수 {len(mine)})")
    p = mine[0]
    if not isinstance(p.get("test_sql"), str) or not p["test_sql"].strip():
        raise ProposalFormatError("test_sql 이 없습니다")
    if not isinstance(p.get("evidence"), list) or not all(isinstance(e, str) for e in p["evidence"]):
        raise ProposalFormatError("evidence 는 문자열 배열이어야 합니다")
    if p.get("confidence") not in CONFIDENCE:
        raise ProposalFormatError(f"confidence 는 {CONFIDENCE} 중 하나여야 합니다")
    if not isinstance(p.get("cause"), str):
        raise ProposalFormatError("cause 가 없습니다")
    return p


def user_prompt(item):
    return (f"다음 쿼리 지문 하나를 분석하라.\n"
            f"- cluster: {item['cluster']}\n- qhash: {item['qhash']}\n- log_date: {item['log_date']}\n"
            f"- query_text(값 마스킹): {mask(item.get('query_text') or '')}\n"
            f"도구로 근거를 모은 뒤, 규칙의 출력 형식(JSON 배열)으로만 답하라.")


def converse_loop(client, model_id, tools, item, max_turns, max_tokens):
    """도구 사용 루프. 마지막 텍스트 답과 사용량을 돌려준다. 턴을 다 쓰면 None."""
    messages = [{"role": "user", "content": [{"text": user_prompt(item)}]}]
    usage = {"inputTokens": 0, "outputTokens": 0, "turns": 0, "tool_calls": 0}
    for _ in range(max_turns):
        resp = client.converse(modelId=model_id, system=[{"text": system_prompt()}], messages=messages,
                               toolConfig={"tools": [{"toolSpec": s} for s in SPECS]},
                               inferenceConfig={"maxTokens": max_tokens, "temperature": 0})
        usage["turns"] += 1
        for k in ("inputTokens", "outputTokens"):
            usage[k] += int((resp.get("usage") or {}).get(k, 0))
        msg = resp["output"]["message"]
        messages.append(msg)
        if resp.get("stopReason") != "tool_use":
            return "".join(b.get("text", "") for b in msg.get("content", [])), usage
        results = []
        for block in msg.get("content", []):
            tu = block.get("toolUse")
            if not tu:
                continue
            if usage["tool_calls"] >= MAX_TOOL_CALLS:
                return None, usage
            usage["tool_calls"] += 1
            out, is_err = tools.call(tu.get("name"), tu.get("input"))
            text = json.dumps(common.jsonable(out), ensure_ascii=False)[:TOOL_OUTPUT_LIMIT]
            results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": text}],
                                           "status": "error" if is_err else "success"}})
        messages.append({"role": "user", "content": results})
    return None, usage


def analyze(item, client, tools, model_id, max_turns=8, max_tokens=4096):
    text, usage = converse_loop(client, model_id, tools, item, max_turns, max_tokens)
    base = {"ticket_id": item["ticket_id"], "qhash": item["qhash"], "usage": usage}
    if text is None:
        return dict(base, status="NO_ANSWER", proposal=None, error=f"도구 호출 {max_turns}턴 안에 답이 없습니다")
    try:
        p = validate(parse_proposals(text), item["qhash"])
    except ProposalFormatError as e:
        common.log.warning("AI 출력 형식 오류 ticket=%s: %s", item["ticket_id"], e)
        return dict(base, status="FORMAT_ERROR", proposal=None, error=str(e)[:300])
    return dict(base, status="OK", proposal=p, error=None)


def handler(event, context):
    item = event["ticket"] if "ticket" in event else event
    store = common.connect(common.env("TARGET_HOST", required=True), common.env("AI_SECRET_ARN", required=True),
                           common.env("STORE_DB", "dba"))
    shop = None
    try:
        shop = common.connect(common.env("TARGET_HOST", required=True), common.env("AI_SECRET_ARN", required=True),
                              common.env("SHOP_DB", "shop"))
        tools = Tools(store, shop, item["cluster"], common.env("SHOP_DB", "shop"))
        r = analyze(item, bedrock_client(), tools, common.env("BEDROCK_MODEL_ID", required=True),
                    int(common.env("ANALYZE_MAX_TURNS", "8")), int(common.env("ANALYZE_MAX_TOKENS", "4096")))
    finally:
        store.close()
        if shop is not None:
            shop.close()
    common.log.info("analyze ticket=%s status=%s usage=%s", r["ticket_id"], r["status"], r["usage"])
    return common.jsonable(r)
