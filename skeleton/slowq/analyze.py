"""AI 분석(선택): Claude Code 를 읽기 전용 MCP 와 함께 실행하고, 결과 JSON 을 엄격하게 읽는다."""
import json
import subprocess

REQUIRED = ("qhash", "proposal")


class ProposalFormatError(ValueError):
    """AI 출력이 약속한 JSON 형식이 아닐 때 — 아무것도 검증 · 발행하지 않고 멈춘다."""


def parse_proposals(text):
    try:
        data = json.loads(text[text.index("["): text.rindex("]") + 1])
    except ValueError as e:
        raise ProposalFormatError(f"JSON 배열이 아닙니다: {e}") from e
    if not isinstance(data, list) or not all(isinstance(p, dict) and all(isinstance(p.get(k), str) and p[k] for k in REQUIRED)
                                              for p in data):
        raise ProposalFormatError(f"각 항목에 {REQUIRED} 가 있어야 합니다")
    return data


def claude_cmd(prompt, mcp_config, tools):
    """기본 도구(Read · Bash 등)는 --tools "" 로 모두 끄고, 쓸 MCP 도구만 --allowedTools 로 묻지 않고 실행하게 한다."""
    return ["claude", "-p", prompt, "--mcp-config", mcp_config, "--strict-mcp-config", "--tools", "",
            *(["--allowedTools", *tools] if tools else []), "--output-format", "text"]


def run_claude(prompt, workdir, mcp_config="mcp.json", tools=(), timeout=900):
    """workdir 의 CLAUDE.md · mcp.json 을 쓰는 claude -p 실행."""
    cmd = claude_cmd(prompt, mcp_config, tools)
    out = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"claude 실행 실패 (exit {out.returncode}): {out.stderr[-500:]}")
    return out.stdout
