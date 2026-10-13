"""쿼리 원문의 값을 지운다 — 저장 · AI 전달 전에 반드시."""
import re

PATTERNS = [
    (re.compile(r"'(?:[^'\\]|\\.)*'"), "'?'"),
    (re.compile(r'"(?:[^"\\]|\\.)*"'), '"?"'),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "?"),
    (re.compile(r"(?<![\w.`])-?\d+(?:\.\d+)?(?![\w`])"), "?"),
]


def mask(sql):
    for pat, rep in PATTERNS:
        sql = pat.sub(rep, sql)
    return sql
